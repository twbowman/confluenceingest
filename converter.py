"""Convert Confluence storage format (XHTML) to clean Markdown with YAML frontmatter."""

import re
from datetime import datetime

import yaml
from markdownify import markdownify as md


def confluence_html_to_markdown(html_content: str) -> str:
    """Convert Confluence storage format HTML to clean Markdown body."""
    cleaned = html_content

    # --- Handle Confluence structured macros ---

    # Code blocks → fenced code blocks
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?"
        r"</ac:structured-macro>",
        r"```\n\1\n```",
        cleaned,
        flags=re.DOTALL,
    )

    # Info/Note/Warning/Tip panels → blockquotes with label
    for macro_type in ["info", "note", "warning", "tip"]:
        cleaned = re.sub(
            rf'<ac:structured-macro[^>]*ac:name="{macro_type}"[^>]*>.*?'
            r"<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?"
            r"</ac:structured-macro>",
            rf"> **{macro_type.upper()}**: \1\n",
            cleaned,
            flags=re.DOTALL,
        )

    # Expand macros — extract the body content
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="expand"[^>]*>.*?'
        r"<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?"
        r"</ac:structured-macro>",
        r"\1",
        cleaned,
        flags=re.DOTALL,
    )

    # Table of contents macro → remove (Markdown renderers handle this differently)
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*>.*?</ac:structured-macro>',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    # Self-closing toc
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*/?>',
        "",
        cleaned,
        flags=re.DOTALL,
    )

    # Task lists (checklists) → GitHub-style Markdown checkboxes
    # Handle differently inside vs outside table cells
    # Use placeholders that survive markdownify
    _TABLE_BR_PLACEHOLDER = "%%BR%%"
    _INDENT_PLACEHOLDER = "%%INDENT%%"

    def _parse_task_list(html: str, indent: int = 0) -> list[str]:
        """Recursively parse task lists, handling nested indentation."""
        items = []
        prefix = _INDENT_PLACEHOLDER * indent
        # Find individual tasks at this level (not inside nested task-lists)
        # Process the HTML sequentially to handle interleaved tasks and nested lists
        pos = 0
        while pos < len(html):
            # Find the next task or nested task-list
            task_start = html.find("<ac:task>", pos)
            nested_start = html.find("<ac:task-list>", pos)

            # No more tasks or nested lists
            if task_start == -1 and nested_start == -1:
                break

            # Determine which comes first
            if nested_start != -1 and (task_start == -1 or nested_start < task_start):
                # Find the matching closing tag (handle nesting)
                depth = 0
                search_pos = nested_start
                end_pos = -1
                while search_pos < len(html):
                    next_open = html.find("<ac:task-list>", search_pos)
                    next_close = html.find("</ac:task-list>", search_pos)
                    if next_close == -1:
                        break
                    if next_open != -1 and next_open < next_close:
                        depth += 1
                        search_pos = next_open + len("<ac:task-list>")
                    else:
                        depth -= 1
                        if depth == 0:
                            end_pos = next_close + len("</ac:task-list>")
                            break
                        search_pos = next_close + len("</ac:task-list>")

                if end_pos == -1:
                    break

                # Extract inner content of the nested task-list
                inner_start = nested_start + len("<ac:task-list>")
                inner_end = end_pos - len("</ac:task-list>")
                inner_html = html[inner_start:inner_end]
                items.extend(_parse_task_list(inner_html, indent + 1))
                pos = end_pos
            else:
                # Found a task
                task_end = html.find("</ac:task>", task_start)
                if task_end == -1:
                    break
                task_end += len("</ac:task>")
                task_html = html[task_start:task_end]

                status_match = re.search(
                    r"<ac:task-status>(.*?)</ac:task-status>", task_html
                )
                checked = status_match and status_match.group(1).strip().lower() == "complete"
                checkbox = "[x]" if checked else "[ ]"
                body_match = re.search(
                    r"<ac:task-body>(.*?)</ac:task-body>", task_html, re.DOTALL
                )
                body = body_match.group(1).strip() if body_match else ""
                body = re.sub(r"<[^>]+>", "", body).strip()
                items.append(f"{prefix}- {checkbox} {body}")
                pos = task_end

        return items

    def _convert_task_list(match: re.Match) -> str:
        task_list_html = match.group(0)
        # Strip the outer <ac:task-list> tags
        inner = re.sub(r"^<ac:task-list>", "", task_list_html)
        inner = re.sub(r"</ac:task-list>$", "", inner)
        items = _parse_task_list(inner, indent=0)
        return "\n".join(items) + "\n"

    def _convert_task_list_in_table(match: re.Match) -> str:
        """Convert task lists inside table cells using <br> for line separation."""
        task_list_html = match.group(1)
        inner = re.sub(r"^<ac:task-list>", "", task_list_html)
        inner = re.sub(r"</ac:task-list>$", "", inner)
        items = _parse_task_list(inner, indent=0)
        # Use unicode checkboxes and <br> for tables
        table_items = []
        for item in items:
            # Replace indent placeholders with count for indentation level
            indent_count = item.count(_INDENT_PLACEHOLDER)
            item = item.replace(_INDENT_PLACEHOLDER, "")
            item = re.sub(r"^- \[x\]", "☑", item)
            item = re.sub(r"^- \[ \]", "☐", item)
            # Preserve indentation with non-breaking spaces for nested items
            if indent_count > 0:
                item = "\u00a0\u00a0" * indent_count + item
            table_items.append(item)
        return _TABLE_BR_PLACEHOLDER.join(table_items)

    # First: handle task lists inside table cells (<td> or <th>)
    # Use a greedy match for nested task-lists inside cells
    def _find_and_replace_table_tasks(html: str) -> str:
        """Find task lists inside table cells and convert them."""
        pattern = r"(<t[dh][^>]*>)(.*?)(</t[dh]>)"
        def _replace_cell(m):
            cell_open = m.group(1)
            cell_content = m.group(2)
            cell_close = m.group(3)
            if "<ac:task-list>" not in cell_content:
                return m.group(0)
            # Find the outermost task-list
            tl_start = cell_content.find("<ac:task-list>")
            # Find matching close (handle nesting)
            depth = 0
            search_pos = tl_start
            end_pos = -1
            while search_pos < len(cell_content):
                next_open = cell_content.find("<ac:task-list>", search_pos)
                next_close = cell_content.find("</ac:task-list>", search_pos)
                if next_close == -1:
                    break
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    search_pos = next_open + len("<ac:task-list>")
                else:
                    depth -= 1
                    if depth == 0:
                        end_pos = next_close + len("</ac:task-list>")
                        break
                    search_pos = next_close + len("</ac:task-list>")
            if end_pos == -1:
                return m.group(0)
            task_list_html = cell_content[tl_start:end_pos]
            # Create a fake match object
            class FakeMatch:
                def group(self, n):
                    return task_list_html
            converted = _convert_task_list_in_table(FakeMatch())
            new_content = cell_content[:tl_start] + converted + cell_content[end_pos:]
            return cell_open + new_content + cell_close
        return re.sub(pattern, _replace_cell, html, flags=re.DOTALL)

    cleaned = _find_and_replace_table_tasks(cleaned)

    # Then: handle remaining task lists (outside tables) — match outermost only
    def _replace_outermost_task_lists(html: str) -> str:
        """Find and replace outermost task-list blocks."""
        result = []
        pos = 0
        while pos < len(html):
            tl_start = html.find("<ac:task-list>", pos)
            if tl_start == -1:
                result.append(html[pos:])
                break
            result.append(html[pos:tl_start])
            # Find matching close
            depth = 0
            search_pos = tl_start
            end_pos = -1
            while search_pos < len(html):
                next_open = html.find("<ac:task-list>", search_pos)
                next_close = html.find("</ac:task-list>", search_pos)
                if next_close == -1:
                    break
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    search_pos = next_open + len("<ac:task-list>")
                else:
                    depth -= 1
                    if depth == 0:
                        end_pos = next_close + len("</ac:task-list>")
                        break
                    search_pos = next_close + len("</ac:task-list>")
            if end_pos == -1:
                result.append(html[tl_start:])
                break
            # Create a fake match for _convert_task_list
            task_list_str = html[tl_start:end_pos]
            class FakeMatch:
                def group(self, n):
                    return task_list_str
            result.append(_convert_task_list(FakeMatch()))
            pos = end_pos
        return "".join(result)

    cleaned = _replace_outermost_task_lists(cleaned)

    # --- Handle images ---
    # Convert <ac:image> with <ri:attachment> to markdown image references.
    # Images with ri:attachment get rewritten to point to the attachments directory.
    # External images (<ri:url>) are preserved as-is.
    # Non-image attachments referenced inline are noted with a comment.
    def _convert_image(match: re.Match) -> str:
        image_html = match.group(0)
        # Check for attachment reference
        att_match = re.search(
            r'<ri:attachment\s+ri:filename="([^"]*)"', image_html
        )
        if att_match:
            filename = att_match.group(1)
            # Return a placeholder that will survive markdownify
            return f'<img alt="{filename}" src="%%ATTACHMENT_PATH%%/{filename}" />'
        # Check for external URL
        url_match = re.search(r'<ri:url\s+ri:value="([^"]*)"', image_html)
        if url_match:
            url = url_match.group(1)
            return f'<img alt="" src="{url}" />'
        return ""

    cleaned = re.sub(
        r"<ac:image[^>]*>.*?</ac:image>",
        _convert_image,
        cleaned,
        flags=re.DOTALL,
    )

    # Remove remaining Confluence-specific XML tags
    cleaned = re.sub(r"<ac:[^>]*>|</ac:[^>]*>", "", cleaned)
    cleaned = re.sub(r"<ri:[^>]*>|</ri:[^>]*>", "", cleaned)

    # --- Convert HTML to Markdown ---
    markdown_body = md(cleaned, heading_style="ATX")

    # Restore line breaks in table cells
    markdown_body = markdown_body.replace(_TABLE_BR_PLACEHOLDER, "<br>")

    # Restore indentation for nested task lists
    markdown_body = markdown_body.replace(_INDENT_PLACEHOLDER, "  ")

    # Clean up excessive whitespace
    markdown_body = re.sub(r"\n{3,}", "\n\n", markdown_body)
    markdown_body = markdown_body.strip()

    return markdown_body


def build_frontmatter(page: dict, space_key: str) -> dict:
    """Extract structured metadata from a Confluence page into frontmatter fields."""
    labels = [
        label["name"]
        for label in page.get("metadata", {}).get("labels", {}).get("results", [])
    ]

    ancestors = [ancestor["title"] for ancestor in page.get("ancestors", [])]

    version_info = page.get("version", {})
    last_modified = version_info.get("when", "")
    last_author = version_info.get("by", {}).get("displayName", "")

    # Parse and normalize the date
    modified_date = ""
    if last_modified:
        try:
            dt = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
            modified_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            modified_date = last_modified

    frontmatter = {
        "id": page["id"],
        "title": page["title"],
        "space": space_key,
        "source_url": f"{page.get('_links', {}).get('base', '')}{page.get('_links', {}).get('webui', '')}",
        "last_modified": modified_date,
        "last_author": last_author,
        "version": version_info.get("number", 1),
    }

    if labels:
        frontmatter["labels"] = labels

    if ancestors:
        frontmatter["breadcrumb"] = ancestors
        frontmatter["parent"] = ancestors[-1] if ancestors else ""

    return frontmatter


def convert_page(page: dict, space_key: str) -> str:
    """
    Convert a full Confluence page to a Markdown document with YAML frontmatter.

    Returns the complete file content ready to write.
    """
    html_content = page.get("body", {}).get("storage", {}).get("value", "")
    if not html_content:
        return ""

    frontmatter = build_frontmatter(page, space_key)
    markdown_body = confluence_html_to_markdown(html_content)

    # Add the page title as H1
    title = page["title"]
    document = f"---\n{yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()}\n---\n\n# {title}\n\n{markdown_body}\n"

    return document
