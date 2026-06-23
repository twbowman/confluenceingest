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

    # Table of contents macro → remove the macro itself
    # The toc macro never has real body content. However, some Confluence pages
    # have page content interleaved between malformed toc open/close tags.
    # Strategy: remove self-closing or truly empty toc macros, then strip just
    # the toc tags (preserving any content between them).
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*/\s*>',
        "",
        cleaned,
        flags=re.DOTALL,
    )
    # Remove opening toc tag (preserves content after it)
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*>',
        "",
        cleaned,
        flags=re.DOTALL,
    )

    # Status macro → inline badge text
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="status"[^>]*>.*?'
        r'<ac:parameter ac:name="title">([^<]*)</ac:parameter>.*?'
        r"</ac:structured-macro>",
        r"**[\1]**",
        cleaned,
        flags=re.DOTALL,
    )

    # Noformat / preformatted text → fenced code blocks (no language)
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="noformat"[^>]*>.*?'
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?"
        r"</ac:structured-macro>",
        r"```\n\1\n```",
        cleaned,
        flags=re.DOTALL,
    )

    # Panel macro → blockquote (may have a title parameter)
    def _convert_panel(match: re.Match) -> str:
        panel_html = match.group(0)
        title_match = re.search(
            r'<ac:parameter ac:name="title">([^<]*)</ac:parameter>', panel_html
        )
        body_match = re.search(
            r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", panel_html, re.DOTALL
        )
        body = body_match.group(1) if body_match else ""
        if title_match:
            return f"> **{title_match.group(1)}**\n>\n> {body}\n"
        return f"> {body}\n"

    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="panel"[^>]*>.*?</ac:structured-macro>',
        _convert_panel,
        cleaned,
        flags=re.DOTALL,
    )

    # Quote macro → blockquote
    def _convert_quote(match: re.Match) -> str:
        body_match = re.search(
            r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", match.group(0), re.DOTALL
        )
        body = body_match.group(1).strip() if body_match else ""
        # Strip HTML tags for clean blockquote
        body = re.sub(r"<[^>]+>", "", body).strip()
        lines = body.split("\n")
        return "\n".join(f"> {line}" for line in lines) + "\n"

    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="quote"[^>]*>.*?</ac:structured-macro>',
        _convert_quote,
        cleaned,
        flags=re.DOTALL,
    )

    # Anchor macro → placeholder that becomes HTML anchor after markdownify
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="anchor"[^>]*>.*?'
        r'<ac:parameter ac:name="">([^<]*)</ac:parameter>.*?'
        r"</ac:structured-macro>",
        r'KBANCHORxSTARTx\1xENDx',
        cleaned,
        flags=re.DOTALL,
    )
    # Anchor with named parameter variant
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="anchor"[^>]*>.*?'
        r'<ac:parameter ac:name="[^"]*">([^<]*)</ac:parameter>.*?'
        r"</ac:structured-macro>",
        r'KBANCHORxSTARTx\1xENDx',
        cleaned,
        flags=re.DOTALL,
    )

    # Details/summary (collapsible) → placeholder that becomes <details> after markdownify
    _DETAILS_START = "KBDETAILSOPEN"
    _DETAILS_END = "KBDETAILSCLOSE"
    _SUMMARY_START = "KBSUMMARYOPEN"
    _SUMMARY_END = "KBSUMMARYCLOSE"

    def _convert_details(match: re.Match) -> str:
        macro_html = match.group(0)
        title_match = re.search(
            r'<ac:parameter ac:name="title">([^<]*)</ac:parameter>', macro_html
        )
        body_match = re.search(
            r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", macro_html, re.DOTALL
        )
        summary = title_match.group(1) if title_match else "Details"
        body = body_match.group(1) if body_match else ""
        return f"{_DETAILS_START}{_SUMMARY_START}{summary}{_SUMMARY_END}\n\n{body}\n\n{_DETAILS_END}\n"

    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="details"[^>]*>.*?</ac:structured-macro>',
        _convert_details,
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(
        r'<ac:structured-macro[^>]*ac:name="detail"[^>]*>.*?</ac:structured-macro>',
        _convert_details,
        cleaned,
        flags=re.DOTALL,
    )

    # Fallback: any remaining structured macros — extract their body content
    # rather than losing it entirely. Preserves text from unknown/custom macros.
    def _extract_macro_body(match: re.Match) -> str:
        macro_html = match.group(0)
        # Identify the macro name for reference
        name_match = re.search(r'ac:name="([^"]*)"', macro_html)
        macro_name = name_match.group(1) if name_match else "unknown"
        # Try rich-text-body first (contains HTML content)
        body_match = re.search(
            r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", macro_html, re.DOTALL
        )
        if body_match:
            return body_match.group(1)
        # Try plain-text-body (contains raw text in CDATA)
        plain_match = re.search(
            r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>",
            macro_html, re.DOTALL,
        )
        if plain_match:
            return f"```\n{plain_match.group(1)}\n```"
        # No body — macro is dynamic or has no static content
        # Leave a visible marker so it's clear content was omitted
        return f"KBMACRODROPxSTARTx{macro_name}xENDx"

    cleaned = re.sub(
        r"<ac:structured-macro[^>]*>.*?</ac:structured-macro>",
        _extract_macro_body,
        cleaned,
        flags=re.DOTALL,
    )

    # --- Handle user mentions ---
    # Confluence stores @mentions as <ac:link><ri:user ri:userkey="..." /></ac:link>
    # Convert to @username or @userkey so mentions survive tag removal AND task body parsing.
    def _convert_user_mention(match: re.Match) -> str:
        mention_html = match.group(0)
        # Try username first (human-readable)
        username_match = re.search(r'ri:username="([^"]*)"', mention_html)
        if username_match:
            return f"@{username_match.group(1)}"
        # Try account-id (Confluence Cloud)
        account_match = re.search(r'ri:account-id="([^"]*)"', mention_html)
        if account_match:
            return f"@{account_match.group(1)}"
        # Fall back to userkey (opaque, but preserves the reference)
        key_match = re.search(r'ri:userkey="([^"]*)"', mention_html)
        if key_match:
            return f"@{key_match.group(1)}"
        return "@unknown"

    cleaned = re.sub(
        r"<ac:link[^>]*>\s*<ri:user[^/]*/>\s*</ac:link>",
        _convert_user_mention,
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
                # Found a task — need to find its matching </ac:task> (handle nesting)
                depth = 0
                search_pos = task_start
                task_end = -1
                while search_pos < len(html):
                    next_open = html.find("<ac:task>", search_pos + 1 if search_pos == task_start else search_pos)
                    next_close = html.find("</ac:task>", search_pos + 1 if search_pos == task_start else search_pos)
                    if next_close == -1:
                        break
                    # First iteration: count the opening tag we started with
                    if search_pos == task_start:
                        depth = 1
                        search_pos = task_start + len("<ac:task>")
                        continue
                    if next_open != -1 and next_open < next_close:
                        depth += 1
                        search_pos = next_open + len("<ac:task>")
                    else:
                        depth -= 1
                        if depth == 0:
                            task_end = next_close + len("</ac:task>")
                            break
                        search_pos = next_close + len("</ac:task>")

                if task_end == -1:
                    break

                task_html = html[task_start:task_end]

                # Extract status only from the task's own level (before any nested task)
                # This prevents picking up a child task's status when the parent's
                # status appears after the body in some Confluence versions.
                body_start_pos = task_html.find("<ac:task-body>")
                nested_task_pos = task_html.find("<ac:task>", len("<ac:task>"))
                # Look for status in the safest region: before body or before nested task
                search_boundary = len(task_html)
                if body_start_pos != -1:
                    search_boundary = body_start_pos
                if nested_task_pos != -1 and nested_task_pos < search_boundary:
                    search_boundary = nested_task_pos

                # First try: find status before the body/nested content
                status_region = task_html[:search_boundary]
                status_match = re.search(
                    r"<ac:task-status>(.*?)</ac:task-status>", status_region
                )
                if not status_match:
                    # Fallback: status might be after the body (some Confluence versions)
                    # Look after the last </ac:task-body> at the top level
                    body_end_pos = task_html.rfind("</ac:task-body>")
                    if body_end_pos != -1:
                        after_body = task_html[body_end_pos:]
                        status_match = re.search(
                            r"<ac:task-status>(.*?)</ac:task-status>", after_body
                        )

                # Confluence uses "complete" or "DONE" for checked; "incomplete" for unchecked
                checked = status_match and status_match.group(1).strip().lower() != "incomplete"
                checkbox = "[x]" if checked else "[ ]"

                # Extract body — use greedy match to get the full body including nested content
                body_match = re.search(
                    r"<ac:task-body>(.*)</ac:task-body>", task_html, re.DOTALL
                )
                body_html = body_match.group(1).strip() if body_match else ""

                # Check if the body contains a nested task-list
                nested_in_body = re.search(
                    r"(<ac:task-list>.*</ac:task-list>)", body_html, re.DOTALL
                )
                if nested_in_body:
                    # Extract text before the nested list as this task's body
                    text_before = body_html[:nested_in_body.start()]
                    text_before = re.sub(r"<[^>]+>", "", text_before).strip()
                    items.append(f"{prefix}- {checkbox} {text_before}")
                    # Process the nested task-list as children
                    nested_html = nested_in_body.group(1)
                    inner = nested_html[len("<ac:task-list>"):-len("</ac:task-list>")]
                    items.extend(_parse_task_list(inner, indent + 1))
                else:
                    # No nested list — just extract the text
                    body = re.sub(r"<[^>]+>", "", body_html).strip()
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

    # Restore HTML anchors
    markdown_body = re.sub(
        r"KBANCHORxSTARTx([^x]+)xENDx",
        r'<a id="\1"></a>',
        markdown_body,
    )

    # Restore <details> blocks
    markdown_body = markdown_body.replace("KBDETAILSOPEN", "<details>\n")
    markdown_body = markdown_body.replace("KBDETAILSCLOSE", "</details>")
    markdown_body = markdown_body.replace("KBSUMMARYOPEN", "<summary>")
    markdown_body = markdown_body.replace("KBSUMMARYCLOSE", "</summary>")

    # Restore dropped macro markers
    markdown_body = re.sub(
        r"KBMACRODROPxSTARTx([^x]+)xENDx",
        r"<!-- Confluence macro: \1 (no static content) -->",
        markdown_body,
    )

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
