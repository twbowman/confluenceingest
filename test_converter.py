"""
Tests for Confluence → Markdown conversion.

Covers known conversion issues that have been fixed:
1. Task lists (checkboxes) not converting at all
2. Checkbox items rendering on a single line (missing newlines)
3. Checkboxes inside tables collapsing to one line
4. Nested/indented checkboxes losing hierarchy

Run with: python -m pytest test_converter.py -v
"""

import pytest
from converter import confluence_html_to_markdown


# ─────────────────────────────────────────────────────────────
# 1. Basic task list conversion
# ─────────────────────────────────────────────────────────────


class TestTaskListBasic:
    """Task lists should convert to GitHub-style Markdown checkboxes."""

    def test_complete_task_converts_to_checked(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Done item</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        assert "- [x] Done item" in result

    def test_incomplete_task_converts_to_unchecked(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Pending item</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        assert "- [ ] Pending item" in result

    def test_task_body_html_tags_stripped(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span class=\"placeholder\"><strong>Bold</strong> text</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        assert "- [x] Bold text" in result

    def test_empty_task_list_produces_no_checkboxes(self):
        html = "<ac:task-list></ac:task-list>"
        result = confluence_html_to_markdown(html)
        assert "- [" not in result


# ─────────────────────────────────────────────────────────────
# 2. Multiple checkbox items on separate lines
# ─────────────────────────────────────────────────────────────


class TestTaskListNewlines:
    """Each checkbox item must be on its own line."""

    def test_multiple_tasks_on_separate_lines(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>First</span></ac:task-body>"
            "</ac:task>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Second</span></ac:task-body>"
            "</ac:task>"
            "<ac:task><ac:task-id>3</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Third</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        lines = [l for l in result.splitlines() if l.strip().startswith("- [")]
        assert len(lines) == 3
        assert "- [x] First" in lines[0]
        assert "- [ ] Second" in lines[1]
        assert "- [x] Third" in lines[2]

    def test_items_not_concatenated_on_single_line(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>A</span></ac:task-body>"
            "</ac:task>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>B</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        # Should NOT have both items on the same line
        for line in result.splitlines():
            assert not ("- [x] A" in line and "- [ ] B" in line)


# ─────────────────────────────────────────────────────────────
# 3. Checkboxes inside table cells
# ─────────────────────────────────────────────────────────────


class TestTaskListInTable:
    """Task lists inside tables use <br> and unicode checkboxes."""

    def test_table_checkboxes_separated_by_br(self):
        html = (
            "<table><tr><th>Tasks</th></tr><tr><td>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Deploy</span></ac:task-body>"
            "</ac:task>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Test</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</td></tr></table>"
        )
        result = confluence_html_to_markdown(html)
        assert "<br>" in result
        assert "☑ Deploy" in result
        assert "☐ Test" in result

    def test_table_checkboxes_use_unicode_symbols(self):
        html = (
            "<table><tr><td>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Done</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</td></tr></table>"
        )
        result = confluence_html_to_markdown(html)
        assert "☑" in result
        # Should NOT use - [x] syntax inside tables
        assert "- [x]" not in result

    def test_table_structure_preserved(self):
        html = (
            "<table><tr><th>Task</th><th>Owner</th></tr><tr><td>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Ship it</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</td><td>Alice</td></tr></table>"
        )
        result = confluence_html_to_markdown(html)
        # Should be a valid markdown table
        assert "| Task | Owner |" in result
        assert "Alice" in result


# ─────────────────────────────────────────────────────────────
# 4. Nested/indented task lists
# ─────────────────────────────────────────────────────────────


class TestTaskListNested:
    """Nested task lists should preserve indentation hierarchy."""

    def test_single_level_nesting(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Parent</span></ac:task-body>"
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Child</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        lines = result.splitlines()
        parent_line = next(l for l in lines if "Parent" in l)
        child_line = next(l for l in lines if "Child" in l)
        # Parent should not be indented
        assert parent_line.startswith("- [x]")
        # Child should be indented (2 spaces)
        assert child_line.startswith("  - [ ]")

    def test_double_level_nesting(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Level 0</span></ac:task-body>"
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Level 1</span></ac:task-body>"
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>3</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Level 2</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</ac:task-list>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        lines = result.splitlines()
        l0 = next(l for l in lines if "Level 0" in l)
        l1 = next(l for l in lines if "Level 1" in l)
        l2 = next(l for l in lines if "Level 2" in l)
        assert l0.startswith("- [x]")
        assert l1.startswith("  - [ ]")
        assert l2.startswith("    - [x]")

    def test_sibling_after_nested_block(self):
        """A task after a nested block should be at the parent level."""
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>First</span></ac:task-body>"
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Nested</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "<ac:task><ac:task-id>3</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Back to parent</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        lines = result.splitlines()
        back_line = next(l for l in lines if "Back to parent" in l)
        # Should be at root level, not indented
        assert back_line.startswith("- [ ]")

    def test_nested_in_table_uses_nbsp_indentation(self):
        html = (
            "<table><tr><td>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body><span>Parent</span></ac:task-body>"
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            "<ac:task-body><span>Child</span></ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</ac:task-list>"
            "</td></tr></table>"
        )
        result = confluence_html_to_markdown(html)
        assert "☑ Parent" in result
        # Child should have non-breaking space indentation
        assert "\u00a0\u00a0☐ Child" in result


# ─────────────────────────────────────────────────────────────
# Existing conversion features (regression tests)
# ─────────────────────────────────────────────────────────────


class TestExistingConversions:
    """Ensure existing Confluence macro conversions still work."""

    def test_code_block_conversion(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            "<ac:plain-text-body><![CDATA[print('hello')]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = confluence_html_to_markdown(html)
        assert "```" in result
        assert "print('hello')" in result

    def test_info_panel_conversion(self):
        html = (
            '<ac:structured-macro ac:name="info">'
            "<ac:rich-text-body>Important note</ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = confluence_html_to_markdown(html)
        assert "INFO" in result
        assert "Important note" in result
        assert result.strip().startswith(">")

    def test_warning_panel_conversion(self):
        html = (
            '<ac:structured-macro ac:name="warning">'
            "<ac:rich-text-body>Be careful</ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = confluence_html_to_markdown(html)
        assert "WARNING" in result
        assert "Be careful" in result
        assert result.strip().startswith(">")

    def test_toc_macro_removed(self):
        html = (
            '<ac:structured-macro ac:name="toc" ac:schema-version="1">'
            "</ac:structured-macro>"
            "<h1>Title</h1>"
        )
        result = confluence_html_to_markdown(html)
        assert "toc" not in result.lower()
        assert "Title" in result

    def test_expand_macro_content_preserved(self):
        html = (
            '<ac:structured-macro ac:name="expand">'
            "<ac:rich-text-body><p>Hidden content</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = confluence_html_to_markdown(html)
        assert "Hidden content" in result

    def test_headings_convert_to_atx(self):
        html = "<h2>Section Title</h2><p>Body text</p>"
        result = confluence_html_to_markdown(html)
        assert "## Section Title" in result

    def test_tables_convert_to_markdown(self):
        html = (
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table>"
        )
        result = confluence_html_to_markdown(html)
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result


# ─────────────────────────────────────────────────────────────
# 5. Image and attachment handling
# ─────────────────────────────────────────────────────────────


class TestImageConversion:
    """Confluence image macros should convert to markdown image references."""

    def test_attachment_image_converts_to_markdown_img(self):
        html = (
            '<ac:image>'
            '<ri:attachment ri:filename="screenshot.png" />'
            '</ac:image>'
        )
        result = confluence_html_to_markdown(html)
        assert "screenshot.png" in result
        assert "%%ATTACHMENT_PATH%%" in result

    def test_external_url_image_preserved(self):
        html = (
            '<ac:image>'
            '<ri:url ri:value="https://example.com/logo.png" />'
            '</ac:image>'
        )
        result = confluence_html_to_markdown(html)
        assert "https://example.com/logo.png" in result

    def test_image_not_stripped_from_output(self):
        """Images should no longer be stripped — they should appear in output."""
        html = (
            "<p>Before</p>"
            '<ac:image>'
            '<ri:attachment ri:filename="diagram.png" />'
            '</ac:image>'
            "<p>After</p>"
        )
        result = confluence_html_to_markdown(html)
        assert "diagram.png" in result
        assert "Before" in result
        assert "After" in result

    def test_multiple_images_in_page(self):
        html = (
            '<ac:image><ri:attachment ri:filename="first.png" /></ac:image>'
            '<ac:image><ri:attachment ri:filename="second.jpg" /></ac:image>'
        )
        result = confluence_html_to_markdown(html)
        assert "first.png" in result
        assert "second.jpg" in result

    def test_image_with_attributes(self):
        html = (
            '<ac:image ac:width="500" ac:height="300">'
            '<ri:attachment ri:filename="wide-image.png" />'
            '</ac:image>'
        )
        result = confluence_html_to_markdown(html)
        assert "wide-image.png" in result



# ─────────────────────────────────────────────────────────────
# 6. User mentions (@mentions)
# ─────────────────────────────────────────────────────────────


class TestUserMentions:
    """Confluence user mentions should convert to @username format."""

    def test_mention_with_userkey(self):
        html = '<p>Assigned to <ac:link><ri:user ri:userkey="772abc123" /></ac:link></p>'
        result = confluence_html_to_markdown(html)
        assert "@772abc123" in result

    def test_mention_with_username(self):
        html = '<p>Contact <ac:link><ri:user ri:username="jdoe" /></ac:link></p>'
        result = confluence_html_to_markdown(html)
        assert "@jdoe" in result

    def test_mention_with_account_id(self):
        html = '<p>Owner: <ac:link><ri:user ri:account-id="5d123abc" /></ac:link></p>'
        result = confluence_html_to_markdown(html)
        assert "@5d123abc" in result

    def test_mention_username_preferred_over_userkey(self):
        """Username should be used when available (most human-readable)."""
        html = '<p><ac:link><ri:user ri:username="jsmith" ri:userkey="abc123" /></ac:link></p>'
        result = confluence_html_to_markdown(html)
        assert "@jsmith" in result

    def test_mention_inside_task_body(self):
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            '<ac:task-body><span>Review by <ac:link><ri:user ri:userkey="772" /></ac:link></span></ac:task-body>'
            "</ac:task>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        assert "@772" in result
        assert "- [ ] Review by @772" in result

    def test_mention_not_stripped_from_output(self):
        html = '<p>Before <ac:link><ri:user ri:userkey="abc" /></ac:link> after</p>'
        result = confluence_html_to_markdown(html)
        assert "Before" in result
        assert "@abc" in result
        assert "after" in result

    def test_multiple_mentions_in_page(self):
        html = (
            '<p><ac:link><ri:user ri:username="alice" /></ac:link> and '
            '<ac:link><ri:user ri:username="bob" /></ac:link></p>'
        )
        result = confluence_html_to_markdown(html)
        assert "@alice" in result
        assert "@bob" in result


    def test_mention_with_ac_link_attributes(self):
        """ac:link can have extra attributes like ac:anchor — should still resolve."""
        html = '<p><ac:link ac:anchor=""><ri:user ri:userkey="abc123" /></ac:link> did this</p>'
        result = confluence_html_to_markdown(html)
        assert "@abc123" in result

    def test_mention_in_task_with_nested_list(self):
        """User mention in a task body should not break nested task list parsing."""
        html = (
            "<ac:task-list>"
            "<ac:task><ac:task-id>1</ac:task-id>"
            "<ac:task-status>incomplete</ac:task-status>"
            '<ac:task-body><ac:link ac:anchor=""><ri:user ri:userkey="xyz" /></ac:link> Review</ac:task-body>'
            "</ac:task>"
            "<ac:task-list>"
            "<ac:task><ac:task-id>2</ac:task-id>"
            "<ac:task-status>complete</ac:task-status>"
            "<ac:task-body>Nested item</ac:task-body>"
            "</ac:task>"
            "</ac:task-list>"
            "</ac:task-list>"
        )
        result = confluence_html_to_markdown(html)
        assert "@xyz" in result
        assert "Nested item" in result
        lines = result.splitlines()
        parent = next(l for l in lines if "@xyz" in l)
        child = next(l for l in lines if "Nested item" in l)
        assert parent.startswith("- [ ]")
        assert child.startswith("  - [x]")
