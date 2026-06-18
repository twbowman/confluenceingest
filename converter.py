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
    # Use a placeholder for line breaks inside tables that survives markdownify
    _TABLE_BR_PLACEHOLDER = "%%BR%%"

    def _convert_task_list(match: re.Match) -> str:
        task_list_html = match.group(0)
        tasks = re.findall(r"<ac:task>.*?</ac:task>", task_list_html, re.DOTALL)
        items = []
        for task_html in tasks:
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
            items.append(f"- {checkbox} {body}")
        return "\n".join(items) + "\n"

    def _convert_task_list_in_table(match: re.Match) -> str:
        """Convert task lists inside table cells using <br> for line separation."""
        task_list_html = match.group(1)
        tasks = re.findall(r"<ac:task>.*?</ac:task>", task_list_html, re.DOTALL)
        items = []
        for task_html in tasks:
            status_match = re.search(
                r"<ac:task-status>(.*?)</ac:task-status>", task_html
            )
            checked = status_match and status_match.group(1).strip().lower() == "complete"
            checkbox = "☑" if checked else "☐"
            body_match = re.search(
                r"<ac:task-body>(.*?)</ac:task-body>", task_html, re.DOTALL
            )
            body = body_match.group(1).strip() if body_match else ""
            body = re.sub(r"<[^>]+>", "", body).strip()
            items.append(f"{checkbox} {body}")
        return _TABLE_BR_PLACEHOLDER.join(items)

    # First: handle task lists inside table cells (<td> or <th>)
    cleaned = re.sub(
        r"<t[dh][^>]*>.*?(<ac:task-list>.*?</ac:task-list>).*?</t[dh]>",
        lambda m: m.group(0).replace(m.group(1), _convert_task_list_in_table(m)),
        cleaned,
        flags=re.DOTALL,
    )
    # Then: handle remaining task lists (outside tables)
    cleaned = re.sub(
        r"<ac:task-list>.*?</ac:task-list>", _convert_task_list, cleaned, flags=re.DOTALL
    )

    # Remove remaining Confluence-specific XML tags
    cleaned = re.sub(r"<ac:[^>]*>|</ac:[^>]*>", "", cleaned)
    cleaned = re.sub(r"<ri:[^>]*>|</ri:[^>]*>", "", cleaned)

    # --- Convert HTML to Markdown ---
    markdown_body = md(cleaned, heading_style="ATX", strip=["img"])

    # Restore line breaks in table cells
    markdown_body = markdown_body.replace(_TABLE_BR_PLACEHOLDER, "<br>")

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
