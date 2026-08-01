from __future__ import annotations


class GuardedFilesystemBackend:
    def __new__(cls, root_dir, virtual_mode: bool = True):
        from deepagents.backends import FilesystemBackend

        class _GuardedFilesystemBackend(FilesystemBackend):
            CONTEXT_GUARDRAIL_THRESHOLD = 8

            def __init__(self, guarded_root_dir, guarded_virtual_mode: bool = True) -> None:
                super().__init__(root_dir=guarded_root_dir, virtual_mode=guarded_virtual_mode)
                self._failed_edit_counts: dict[tuple[str, str, bool], int] = {}
                self._context_calls_since_write_or_edit = 0

            def ls(self, path: str):
                result = super().ls(path)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def grep(
                self,
                pattern: str,
                path: str | None = None,
                glob: str | None = None,
                *,
                max_count: int | None = None,
                context_lines: int = 0,
            ):
                result = super().grep(pattern, path, glob, max_count=max_count, context_lines=context_lines)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def glob(self, pattern: str, path: str | None = None):
                result = super().glob(pattern, path)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def read(
                self,
                file_path: str,
                offset: int = 0,
                limit: int = 2000,
            ):
                result = super().read(file_path, offset, limit)
                should_warn = self._record_context_call()
                if (
                    should_warn
                    and result.error is None
                    and result.file_data is not None
                    and result.file_data.get("encoding") == "utf-8"
                ):
                    result.file_data["content"] = (
                        f"{result.file_data['content']}\n\n"
                        f"{context_guardrail_message()} "
                        "This narrow read is allowed so you can use the visible line numbers."
                    )
                return result

            def _record_context_call(self) -> bool:
                self._context_calls_since_write_or_edit += 1
                return self._context_calls_since_write_or_edit > self.CONTEXT_GUARDRAIL_THRESHOLD

            def write(
                self,
                file_path: str,
                content: str,
            ):
                self._context_calls_since_write_or_edit = 0
                return super().write(file_path, content)

            def edit(
                self,
                file_path: str,
                old_string: str,
                new_string: str,
                replace_all: bool = False,
            ):
                self._context_calls_since_write_or_edit = 0
                result = super().edit(file_path, old_string, new_string, replace_all)
                if result.error is None:
                    self._failed_edit_counts.pop((file_path, old_string, replace_all), None)
                    return result

                key = (file_path, old_string, replace_all)
                count = self._failed_edit_counts.get(key, 0) + 1
                self._failed_edit_counts[key] = count
                if count >= 2:
                    result.error = (
                        f"{result.error}\n\n"
                        "GUARDRAIL: This exact edit_file call has failed repeatedly. "
                        "Do not call edit_file again with the same old_string. "
                        "Read the current target region again, then use a smaller exact replacement "
                        "or rewrite the full file with write_file."
                    )
                return result

        return _GuardedFilesystemBackend(root_dir, virtual_mode)


def context_guardrail_message() -> str:
    return (
        "GUARDRAIL: Too many context-gathering tool calls have happened without a patch. "
        "Stop searching/listing. If you have line numbers, call replace_line_range now. "
        "If one final look is required, read one narrow target region only."
    )
