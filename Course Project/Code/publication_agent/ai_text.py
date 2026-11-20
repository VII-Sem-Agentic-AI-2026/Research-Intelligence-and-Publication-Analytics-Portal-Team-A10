"""Extract visible text from provider responses without exposing reasoning blocks."""


def response_text(response):
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in content
            if isinstance(block, str) or (
                isinstance(block, dict) and block.get("type") == "text"
                and not block.get("thought")
            )
        )
    return ""
