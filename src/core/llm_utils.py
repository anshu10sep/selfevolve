"""
LLM Response Utilities

Handles differences in LLM response formats across model versions.
Some models return response.content as a string, others as a list of blocks.
"""


def extract_text(content) -> str:
    """
    Normalize LLM response content to a plain string.

    Args:
        content: response.content from a LangChain LLM call.
                 May be a str, list, or other type depending on the model.

    Returns:
        A plain string with all content joined.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", str(block)))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)
