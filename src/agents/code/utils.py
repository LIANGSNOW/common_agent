import json
import re
from typing import Any

BACKTICK_PATTERN = r"<execute>\s*(.*?)\s*</execute>"
TOOL_PATTERN = r"<(\w+)>\{(.*?)\}</\1>"


def extract_tool_command(text: str) -> dict[str, dict[str, Any]] | None:
    """从文本中提取工具命令。

    解析格式为 <tool_name>{arg1=value1, arg2=value2, ...}</tool_name> 的工具命令。

    Args:
        text: 包含工具命令的文本。

    Returns:
        Optional[Dict[str, dict]]: 工具命令字典，格式为 {tool_name: {参数dict}}。
            如果未找到工具命令，返回None。

    Example:
        >>> text = '<add>{a=1, b=2}</add>'
        >>> extract_tool_command(text)
        {'add': {'a': 1, 'b': 2}}
    """
    matches: list[tuple[str, str]] = re.findall(TOOL_PATTERN, text, re.DOTALL)

    if not matches:
        return None

    result: dict[Any, Any] = {}

    for tool_name, params_str in matches:
        # 解析参数字符串，转换为dict
        params: dict[str, Any] = {}
        if params_str.strip():
            # 尝试两种格式: JSON格式和Python dict格式
            try:
                # 首先尝试作为JSON解析 (格式: {"key": "value"})
                params = json.loads(params_str)
                if not isinstance(params, dict):
                    params = {}
            except (json.JSONDecodeError, ValueError):
                # 如果JSON解析失败，尝试Python dict格式 (格式: key=value, key2=value2)
                try:
                    params_dict = eval(f"dict({params_str})")
                    if isinstance(params_dict, dict):
                        params = params_dict
                except Exception:
                    # 如果两种格式都失败，参数保持为空dict
                    params = {}

        result[tool_name] = params

    return result


def extract_and_combine_codeblocks(text: str) -> str:
    code_blocks: list[str] = re.findall(BACKTICK_PATTERN, text, re.DOTALL)

    if not code_blocks:
        return ""

    # Process each codeblock
    processed_blocks: list[str] = []
    for block in code_blocks:
        # Strip leading and trailing whitespace
        block: str = block.strip()

        # If the first line looks like a language identifier, remove it
        lines: list[str] = block.split("\n")
        if lines and (not lines[0].strip() or " " not in lines[0].strip()):
            # First line is empty or likely a language identifier (no spaces)
            block = "\n".join(lines[1:])

        processed_blocks.append(block)

    # Combine all codeblocks with newlines between them
    combined_code: str = "\n\n".join(processed_blocks)
    return combined_code
