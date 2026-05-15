from pathlib import Path as RealPath

from pipeline import runner as pipeline_entry


class FakePath:
    files: dict[str, bytes] = {}

    def __init__(self, value):
        self.value = str(getattr(value, "value", value)).replace("\\", "/")

    def __truediv__(self, child):
        return FakePath(f"{self.value}/{child}")

    def __str__(self):
        return self.value

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.value)

    def resolve(self):
        return self

    def exists(self):
        return self.value in self.files

    def is_file(self):
        return self.exists()

    def read_bytes(self):
        return self.files[self.value]

    def write_bytes(self, data):
        self.files[self.value] = data


class TestRequirementInput:
    def setup_method(self):
        FakePath.files = {}

    def test_prepare_requirement_copies_specified_file(self, mocker):
        FakePath.files["request.md"] = "新需求内容".encode("utf-8")
        mocker.patch.object(pipeline_entry, "Path", FakePath)

        result = pipeline_entry._prepare_requirement_input(
            "request.md", FakePath(".ai-dev"), mocker.MagicMock()
        )

        assert result == ".ai-dev/requirement-raw.md"
        assert FakePath.files[".ai-dev/requirement-raw.md"] == "新需求内容".encode("utf-8")

    def test_prepare_requirement_uses_existing_raw_when_no_req(self, mocker):
        FakePath.files[".ai-dev/requirement-raw.md"] = "已有需求".encode("utf-8")
        mocker.patch.object(pipeline_entry, "Path", FakePath)

        result = pipeline_entry._prepare_requirement_input(
            "", FakePath(".ai-dev"), mocker.MagicMock()
        )

        assert result == ".ai-dev/requirement-raw.md"

    def test_prepare_requirement_guided_paste_when_missing_file(self, mocker):
        mocker.patch.object(pipeline_entry, "Path", FakePath)
        mocker.patch("builtins.input", side_effect=["2", "粘贴的新需求", "EOF"])

        result = pipeline_entry._prepare_requirement_input(
            "missing.md", FakePath(".ai-dev"), mocker.MagicMock(), interactive=True
        )

        assert result == ".ai-dev/requirement-raw.md"
        assert FakePath.files[".ai-dev/requirement-raw.md"] == "粘贴的新需求\n".encode("utf-8")

    def test_prepare_requirement_guided_existing_requires_choice(self, mocker):
        FakePath.files[".ai-dev/requirement-raw.md"] = "已有需求".encode("utf-8")
        mocker.patch.object(pipeline_entry, "Path", FakePath)
        mocker.patch("builtins.input", side_effect=["3"])

        result = pipeline_entry._prepare_requirement_input(
            "", FakePath(".ai-dev"), mocker.MagicMock(), interactive=True
        )

        assert result == ".ai-dev/requirement-raw.md"

    def test_prepare_requirement_rejects_empty_file(self, mocker):
        FakePath.files["empty.md"] = b"   \n"
        mocker.patch.object(pipeline_entry, "Path", FakePath)

        try:
            pipeline_entry._prepare_requirement_input(
                "empty.md", FakePath(".ai-dev"), mocker.MagicMock()
            )
            assert False, "should reject empty requirement file"
        except ValueError:
            pass


class TestOutputFreshness:
    def test_output_refreshed_detects_unchanged_existing_file(self, mocker):
        path = RealPath("requirement.md")
        mocker.patch.object(pipeline_entry, "_file_fingerprint", return_value=("same",))

        assert pipeline_entry._output_refreshed(path, ("same",)) is False

    def test_output_refreshed_detects_changed_file(self, mocker):
        path = RealPath("requirement.md")
        mocker.patch.object(pipeline_entry, "_file_fingerprint", return_value=("new",))

        assert pipeline_entry._output_refreshed(path, ("old",)) is True

    def test_output_refreshed_detects_new_file(self, mocker):
        path = RealPath("requirement.md")
        mocker.patch.object(pipeline_entry, "_file_fingerprint", return_value=("new",))

        assert pipeline_entry._output_refreshed(path, None) is True
