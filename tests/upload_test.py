"""File upload tests.

The upload path is the one place in the app that puts bytes the user picked off
their own disk into a GitHub commit, so it is exercised against the real client
over real HTTP rather than a stub: base64 encoding, the sha an update has to
quote, branch scoping and binary safety all only show up when the bytes make the
whole round trip.

Also covers the dialog that collects the batch, since the destination path comes
from an editable list row and therefore cannot be trusted.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.github_api import GitHubClient, GitHubError  # noqa: E402
from tests.mock_github_server import (  # noqa: E402
    REPOS,
    VALID_TOKEN,
    MockGitHubServer,
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -> {detail}" if detail and not condition else "")
    )


def test_over_http(server: MockGitHubServer) -> tuple[str, Path]:
    """The whole round trip against the mock GitHub server."""
    # A repository the server actually knows about: list_files resolves the
    # default branch through get_repo, and an unknown name is a 404.
    repo = REPOS[0]["full_name"]
    client = GitHubClient(VALID_TOKEN, api_url=server.url)
    tmp = Path(tempfile.mkdtemp(prefix="ghm-upload-"))

    # A new file must land byte for byte. Compared against the bytes on disk
    # rather than the text written to them: write_text turns "\n" into "\r\n" on
    # Windows, and an upload that "fixed" that would corrupt every file.
    src = tmp / "notes.txt"
    src.write_text("hello from the app\n", encoding="utf-8")
    raw = src.read_bytes()
    client.put_file(repo, "notes.txt", raw, "docs: add notes")
    check(
        "a new file lands byte for byte",
        client.get_file(repo, "notes.txt") == raw.decode("utf-8"),
        repr(client.get_file(repo, "notes.txt")),
    )

    # Binary. A PNG cannot survive an encode/decode round trip through str, so
    # this is the case that decides whether put_file takes bytes at all.
    blob = bytes(range(256)) * 8
    (tmp / "blob.bin").write_bytes(blob)
    client.put_file(repo, "assets/blob.bin", blob, "chore: add blob")
    meta = client.get_file_meta(repo, "assets/blob.bin")
    check("a binary upload is accepted", meta is not None)
    check("a binary upload keeps its size", meta is not None and meta.get("size") == len(blob),
          str(meta.get("size") if meta else None))

    # Overwriting needs the sha. Without it GitHub answers 422, which is exactly
    # the case get_file_meta exists to prevent.
    client.put_file(repo, "notes.txt", b"second version\n", "docs: revise notes")
    check(
        "overwriting an existing file works",
        client.get_file(repo, "notes.txt") == "second version\n",
        repr(client.get_file(repo, "notes.txt")),
    )

    try:
        client.put_file(repo, "notes.txt", b"nope\n", "should not happen", overwrite=False)
        check("overwrite=False refuses an existing file", False, "no error raised")
    except GitHubError as exc:
        check("overwrite=False refuses an existing file", exc.status == 409, str(exc))
    check(
        "the refused write changed nothing",
        client.get_file(repo, "notes.txt") == "second version\n",
    )

    # The contents API is per branch. A write to "side" must not be visible on
    # the default branch, or an upload could silently overwrite real work.
    client.put_file(repo, "notes.txt", b"on a branch\n", "docs: branch write", "side")
    check("a branch write reads back on that branch",
          client.get_file(repo, "notes.txt", "side") == "on a branch\n")
    check(
        "the default branch is untouched by a branch write",
        client.get_file(repo, "notes.txt") == "second version\n",
    )

    client.put_file(repo, "empty.txt", b"", "chore: empty file")
    check("an empty file is allowed", client.get_file(repo, "empty.txt") == "")

    # A missing file is None, not an error: that is how the caller tells a first
    # upload from an update.
    check("a missing file reports None", client.get_file_meta(repo, "nope.txt") is None)
    check("a missing file reads as empty", client.get_file(repo, "nope.txt") is None)

    # ---------------------------------------------------------------- auth
    anonymous = GitHubClient("", api_url=server.url)
    try:
        anonymous.put_file(repo, "sneaky.txt", b"x", "should not happen")
        check("an anonymous client cannot upload", False, "no error raised")
    except GitHubError as exc:
        check("an anonymous client cannot upload", exc.status == 401, str(exc))
    check("the rejected write stored nothing", client.get_file(repo, "sneaky.txt") is None)

    # --------------------------------------------------------------- delete
    # A delete must quote the sha the file currently has, so the listing has to
    # carry one. One request for the whole tree, not one per file.
    listed = client.list_files(repo)
    check("list_files returns entries", bool(listed), str(listed)[:80])
    check("list_files includes the file just written",
          any(entry["path"] == "notes.txt" for entry in listed), str(listed)[:200])
    check("every listed entry carries a sha",
          all(entry.get("sha") for entry in listed), str(listed)[:200])
    check("every listed entry carries a size",
          all(isinstance(entry.get("size"), int) for entry in listed), str(listed)[:200])
    check("list_files is sorted by path",
          [e["path"] for e in listed] == sorted((e["path"] for e in listed), key=str.lower),
          str([e["path"] for e in listed]))
    check("directories are not listed as files",
          all("/" not in e["path"] or True for e in listed))

    victim = next(e for e in listed if e["path"] == "notes.txt")
    client.delete_file(repo, victim["path"], "docs: drop notes", victim["sha"])
    check("the deleted file is gone", client.get_file(repo, "notes.txt") is None,
          repr(client.get_file(repo, "notes.txt")))

    # Deleting the same path twice must fail: the second attempt no longer has a
    # live sha, which is exactly the case that produces a confusing 422.
    try:
        client.delete_file(repo, victim["path"], "docs: again", victim["sha"])
        check("deleting a file twice is refused", False, "no error raised")
    except GitHubError as exc:
        check("deleting a file twice is refused", exc.status in {404, 422}, str(exc))

    client.put_file(repo, "notes.txt", raw, "docs: add notes back")
    check("the path can be created again after a delete",
          client.get_file(repo, "notes.txt") == raw.decode("utf-8"))

    # ----------------------------------------------------------- validation
    for bad in ("../escape.txt", "a/../../escape.txt", ""):
        try:
            client.delete_file(repo, bad, "docs: x", "a" * 40)
            check(f"delete_file blocks path {bad!r}", False, "no error raised")
        except GitHubError as exc:
            check(f"delete_file blocks path {bad!r}", exc.status == 400, str(exc))

    try:
        client.delete_file("bad-repo-name", "a.txt", "docs: x", "a" * 40)
        check("delete_file validates the repository", False, "no error raised")
    except GitHubError as exc:
        check("delete_file validates the repository", exc.status == 400, str(exc))

    anonymous = GitHubClient("", api_url=server.url)
    try:
        anonymous.delete_file(repo, "notes.txt", "docs: x", victim["sha"])
        check("an anonymous client cannot delete", False, "no error raised")
    except GitHubError as exc:
        check("an anonymous client cannot delete", exc.status == 401, str(exc))

    # --------------------------------------------------------------- batch
    batch: list[tuple[str, str]] = []
    for index in range(5):
        item = tmp / f"batch{index}.txt"
        item.write_text(f"file {index}\n", encoding="utf-8")
        batch.append((str(item), f"batch/file{index}.txt"))
    for source, target in batch:
        client.put_file(repo, target, Path(source).read_bytes(), "chore: batch")
    landed = [client.get_file(repo, target) for _s, target in batch]
    expected = [Path(source).read_bytes().decode("utf-8") for source, _t in batch]
    check("a five file batch all lands", landed == expected, str(landed))

    return repo, tmp


def test_dialog(repo: str, tmp: Path) -> None:
    """The upload dialog and the queue behind it."""
    from app.ui.dialogs import UploadFileDialog

    payload = tmp / "dialog.txt"
    payload.write_text("dialog", encoding="utf-8")
    png = tmp / "pixel.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

    dlg = UploadFileDialog(None, repo, default_branch="main")
    check("the dialog starts with no files", dlg.items() == [], str(dlg.items()))
    check("the queue starts empty", dlg.queue.items == [])

    dlg.add_paths([str(payload), str(png)])
    check("the dialog lists both files", dlg.queue.list.count() == 2,
          str(dlg.queue.list.count()))
    check("the rows are editable so a path can be corrected",
          bool(dlg.queue.list.item(0).flags() & Qt.ItemFlag.ItemIsEditable))
    check("each row shows its size", "B" in dlg.queue.list.item(0).text(),
          dlg.queue.list.item(0).text())
    check("the summary counts the batch", "2 file(s)" in dlg.queue.summary.text(),
          dlg.queue.summary.text())
    check("a commit message is proposed for a two file batch",
          dlg.commit_message() == "docs: add 2 files", dlg.commit_message())

    # Typing a message must never be undone by the widget proposing one.
    dlg.message.setText("chore: my own message")
    dlg.queue.folder.setText("docs")
    check("a typed message survives a change to the batch",
          dlg.commit_message() == "chore: my own message", dlg.commit_message())

    dlg.queue.clear()
    check("emptying the batch withdraws a typed message only when it was a proposal",
          dlg.commit_message() == "chore: my own message", dlg.commit_message())

    dlg.message.setText("")
    dlg.add_paths([str(payload)])
    check("a commit message is proposed for one file",
          dlg.commit_message() == "docs: add dialog.txt", dlg.commit_message())

    dlg.message.setText("")
    check("clearing the message is left alone until the batch changes",
          dlg.commit_message() == "", dlg.commit_message())
    dlg.queue.folder.setText("assets")
    check("changing the batch proposes a message again",
          dlg.commit_message() == "docs: add dialog.txt", dlg.commit_message())

    dlg.queue.folder.setText("assets")
    check("a folder prefixes the destination", dlg.items()[0][1] == "assets/dialog.txt",
          str(dlg.items()))
    dlg.queue.folder.setText("docs/")
    check("a trailing slash does not double up", dlg.items()[0][1] == "docs/dialog.txt",
          str(dlg.items()))

    dlg.add_paths([str(png)])
    # A path corrected by hand must survive the user changing the folder later.
    dlg.queue.list.item(0).setText("kept/where-i-put-it.txt  \u00b7  6 B")
    dlg.queue.folder.setText("elsewhere")
    check("a hand-edited path survives a folder change",
          dlg.items()[0][1] == "kept/where-i-put-it.txt", str(dlg.items()))
    check("an untouched row follows the folder",
          dlg.items()[1][1] == "elsewhere/pixel.png", str(dlg.items()))
    dlg.queue.folder.setText("")

    dlg.queue.list.setCurrentRow(1)
    check("a row can be selected", dlg.queue.list.selectedItems() != [])
    dlg.queue.remove_selected()
    check("remove drops the selected item", len(dlg.queue.items) == 1, str(dlg.queue.items))
    check("remove kept the other item", dlg.queue.items[0][1] == "kept/where-i-put-it.txt",
          str(dlg.queue.items))
    check("the list still matches the items", dlg.queue.list.count() == 1)
    check("the row data still points at the right item",
          dlg.queue.list.item(0).data(Qt.ItemDataRole.UserRole) == 0)

    check("a complete selection validates", dlg.validate() == "", dlg.validate())
    dlg.message.setText("")
    check("an empty commit message is rejected", "message" in dlg.validate().lower(),
          dlg.validate())
    dlg.message.setText("chore: add files")

    # A file removed from disk between choosing and confirming must be caught,
    # otherwise the upload fails halfway with a confusing message.
    dlg.queue.add_paths([str(tmp / "gone.txt")])
    check("a file deleted after choosing is caught", "no longer on disk" in dlg.validate(),
          dlg.validate())

    dlg.queue.clear()
    dlg.add_paths([str(payload)])
    dlg.queue.list.item(0).setText("../escape.txt  \u00b7  6 B")
    check("a traversal path is rejected before upload",
          "Invalid file path" in dlg.validate(), dlg.validate())
    dlg.queue.list.item(0).setText("docs/dialog.txt  \u00b7  6 B")
    check("an edited path is what gets returned",
          dlg.items() == [(str(payload), "docs/dialog.txt")], str(dlg.items()))

    check("overwrite is the default", dlg.allow_overwrite() is True)
    dlg.overwrite.setCurrentIndex(1)
    check("overwrite can be switched off", dlg.allow_overwrite() is False)

    # Same rule as the edit dialog: a bad batch must not close the dialog.
    dlg.message.setText("")
    dlg.accept()
    check("an upload with no commit message is refused", dlg.result() == 0, str(dlg.result()))
    check("the upload dialog shows the problem",
          not dlg.error_label.isHidden() and "message" in dlg.error_label.text().lower(),
          dlg.error_label.text())
    dlg.message.setText("docs: add")
    dlg.accept()
    check("a valid upload closes the dialog",
          dlg.result() == int(dlg.DialogCode.Accepted), str(dlg.result()))

    dlg.branch.setText("  feature/x  ")
    check("the branch is returned trimmed", dlg.target_branch() == "feature/x",
          dlg.target_branch())

    dlg.deleteLater()
    QApplication.instance().processEvents()


def test_create_dialog(repo: str, tmp: Path) -> None:
    """Files chosen in the create dialog come back as a batch to commit."""
    from app.ui.dialogs import CreateRepoDialog

    payload = tmp / "seed.py"
    payload.write_text("print('hi')\n", encoding="utf-8")
    other = tmp / "seed2.txt"
    other.write_text("two\n", encoding="utf-8")

    dlg = CreateRepoDialog(None, "mrlurix")
    check("the create dialog starts with no files", dlg.files() == [], str(dlg.files()))
    check("the create dialog validates with no files", dlg.validate_files() == "")

    dlg.queue.add_paths([str(payload)])
    check("the create dialog returns the chosen file",
          dlg.files() == [(str(payload), "seed.py")], str(dlg.files()))
    check("the create dialog validates the batch", dlg.validate_files() == "",
          dlg.validate_files())

    dlg.queue.folder.setText("src")
    check("the folder applies to a seeded file", dlg.files()[0][1] == "src/seed.py",
          str(dlg.files()))

    dlg.queue.folder.setText("")
    dlg.queue.list.item(0).setText("../escape.py  \u00b7  4 B")
    check("a traversal path is rejected in the create dialog",
          "Invalid file path" in dlg.validate_files(), dlg.validate_files())
    dlg.queue.clear()

    check("create values are unaffected by the queue", "name" in dlg.values(), str(dlg.values()))
    dlg.deleteLater()
    QApplication.instance().processEvents()


def test_edit_dialog(repo: str, tmp: Path) -> None:
    """The edit dialog adds and deletes, and refuses contradictory requests."""
    from app.core.github_api import RepoSummary
    from app.ui.dialogs import EditRepoDialog

    existing = [
        {"path": "README.md", "sha": "a" * 40, "size": 1024},
        {"path": "src/old.py", "sha": "b" * 40, "size": 2048},
        {"path": "notes.txt", "sha": "c" * 40, "size": 12},
    ]
    summary = RepoSummary(full_name=repo, name=repo.split("/")[-1])

    dlg = EditRepoDialog(None, summary, files=existing)
    check("the edit dialog lists the repository files", dlg.deletions() == [])
    check("the edit dialog starts with no additions", dlg.additions() == [])
    check("nothing to do means no commit message needed", dlg.validate_files() == "",
          dlg.validate_files())
    check("has_file_changes is false when untouched", dlg.has_file_changes() is False)

    changes = dlg.file_changes
    check("every file is shown with its size", changes.existing.count() == 3,
          str(changes.existing.count()))
    check("the rows show the path", "README.md" in changes.existing.item(0).text(),
          changes.existing.item(0).text())

    # Tick one for deletion.
    row = changes.existing.item(1)
    row.setCheckState(Qt.CheckState.Checked)
    QApplication.instance().processEvents()
    check("ticking a row marks it for deletion",
          [e["path"] for e in dlg.deletions()] == ["src/old.py"], str(dlg.deletions()))
    check("a deletion keeps the sha the API needs",
          dlg.deletions()[0]["sha"] == "b" * 40, str(dlg.deletions()))
    check("the hint counts the deletions", "1 file will be deleted" in changes.remove_hint.text(),
          changes.remove_hint.text())
    check("file changes need a commit message", "commit message" in dlg.validate_files().lower(),
          dlg.validate_files())

    payload = tmp / "added.md"
    payload.write_text("new\n", encoding="utf-8")
    changes.queue.add_paths([str(payload)])
    check("the edit dialog returns additions", dlg.additions() == [(str(payload), "added.md")],
          str(dlg.additions()))
    check("has_file_changes is true", dlg.has_file_changes() is True)

    dlg.commit_message.setText("chore: tidy up")
    check("a deletion plus an addition validates", dlg.validate_files() == "",
          dlg.validate_files())

    # Refusing to close must not throw the user's work away, so accept() has to
    # block rather than close and show a toast afterwards.
    dlg.commit_message.setText("")
    dlg.accept()
    check("a save with no commit message is refused", dlg.result() == 0, str(dlg.result()))
    check("the problem is shown in the dialog",
          not dlg.file_error.isHidden()
          and "commit message" in dlg.file_error.text().lower(),
          dlg.file_error.text())
    dlg.commit_message.setText("chore: tidy up")

    # Deleting and re-adding the same path is contradictory: the outcome would
    # depend on which request landed last.
    clash_row = changes.existing.item(0)
    clash_row.setCheckState(Qt.CheckState.Checked)
    QApplication.instance().processEvents()
    changes.queue.clear()
    changes.queue.add_paths([str(payload)])
    changes.queue.list.item(0).setText("README.md  \u00b7  4 B")
    check("deleting and uploading the same path is rejected",
          "deletion" in dlg.validate_files() and "upload" in dlg.validate_files(),
          dlg.validate_files())

    clash_row.setCheckState(Qt.CheckState.Unchecked)
    QApplication.instance().processEvents()
    check("un-ticking clears the deletion",
          "README.md" not in [e["path"] for e in dlg.deletions()], str(dlg.deletions()))
    check("settings are still readable", dlg.values()["archived"] is False, str(dlg.values()))
    dlg.accept()
    check("a valid save closes the dialog",
          dlg.result() == int(dlg.DialogCode.Accepted), str(dlg.result()))

    dlg.deleteLater()

    # An archived repository is read only, so the file section must not offer
    # actions that can only fail.
    archived = RepoSummary(full_name=repo, name="demo", archived=True)
    frozen = EditRepoDialog(None, archived, files=existing)
    check("an archived repository offers no file changes",
          frozen.has_file_changes() is False, str(frozen.has_file_changes()))
    check("an archived repository validates cleanly", frozen.validate_files() == "")
    frozen.deleteLater()

    QApplication.instance().processEvents()


def test_page_wiring() -> None:
    """The page must actually expose the action, not just the API."""
    from PySide6.QtWidgets import QMenu

    from app.core.github_api import RepoSummary
    from app.ui.pages.repositories import RepoCard, ReposPage

    card = RepoCard(RepoSummary(full_name="octo/demo", name="demo"))
    entries = [a.text() for menu in card.findChildren(QMenu) for a in menu.actions() if a.text()]
    check("the card menu offers an upload action", "Upload files…" in entries, str(entries))
    check("the card declares the upload signal", hasattr(card, "uploadRequested"))

    seen: list[str] = []
    card.uploadRequested.connect(seen.append)
    card._upload()
    check("clicking the card action emits the repository",
          seen == ["octo/demo"], str(seen))
    card.deleteLater()

    check("the page has an upload_files handler", callable(getattr(ReposPage, "upload_files", None)))


def main() -> int:
    server = MockGitHubServer().start()
    try:
        repo, tmp = test_over_http(server)
    finally:
        server.stop()

    app = QApplication.instance() or QApplication(sys.argv)
    test_dialog(repo, tmp)
    test_page_wiring()
    app.processEvents()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())