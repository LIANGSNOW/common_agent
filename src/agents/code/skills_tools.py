import ast
from pathlib import Path
from typing import Any, Callable


SKIP_DIRS = {"__pycache__", ".git"}
SKIP_SUFFIXES = {".pyc"}


def __get_skills_path() -> Path:
    """获取skills目录路径。

    Returns:
        Path: skills 目录的路径。
    """
    return Path(__file__).resolve().parent / "skills"


def get_skill_root(skill_type: str) -> str:
    """获取指定 skill 在磁盘上的绝对路径。

    用于 sandbox 中拷贝模板/资产，例如：
        from src.agents.code.skills_tools import get_skill_root
        root = get_skill_root("ppt")
        shutil.copy(f"{root}/assets/template-swiss.html", "./output/index.html")

    Args:
        skill_type: skill 类别名称（对应 skills/ 下的目录名）。

    Returns:
        str: skill 目录的绝对路径；找不到返回 "Skill not found"。
    """
    skill_path = __get_skills_path() / skill_type
    if not skill_path.is_dir():
        return "Skill not found"
    return str(skill_path.resolve())


def list_skill_files(skill_type: str) -> str:
    """列出指定 skill 目录下所有文件（相对路径），用于按需读取 reference/assets。

    会自动跳过 __pycache__、.pyc 等无关文件。

    Args:
        skill_type: skill 类别名称。

    Returns:
        str: 每行一个相对路径的字符串；找不到返回 "Skill not found"。
    """
    skill_path = __get_skills_path() / skill_type
    if not skill_path.is_dir():
        return "Skill not found"

    entries: list[str] = []
    for path in sorted(skill_path.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(skill_path).parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        entries.append(str(path.relative_to(skill_path)))
    return "\n".join(entries) if entries else "<no files>"


def read_skill_file(skill_type: str, relative_path: str) -> str:
    """读取 skill 目录下任意文本文件内容（references/assets/scripts 等）。

    带路径越界保护——relative_path 不能逃出 skill 目录。
    二进制文件（如 .webp、.png）拒绝读取，避免污染上下文。

    Args:
        skill_type: skill 类别名称。
        relative_path: 相对于 skill 根目录的路径，例如 "references/themes.md"。

    Returns:
        str: 文件内容；失败时返回错误描述字符串。
    """
    skill_path = __get_skills_path() / skill_type
    if not skill_path.is_dir():
        return "Skill not found"

    try:
        target = (skill_path / relative_path).resolve()
        target.relative_to(skill_path.resolve())
    except (ValueError, OSError):
        return f"Invalid path: {relative_path} is outside skill '{skill_type}'"

    if not target.is_file():
        return f"File not found: {relative_path}"

    binary_suffixes = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".woff", ".woff2", ".ttf", ".otf"}
    if target.suffix.lower() in binary_suffixes:
        return f"Binary file refused: {relative_path} (size={target.stat().st_size} bytes). Use file path directly in code."

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Cannot decode as UTF-8: {relative_path}"


def list_skills() -> str:
    """列出skills下所有可用的工具及其模块。

    Returns:
        str: 工具字典，结构为 {工具类别: [工具模块列表]}。
            键为工具类别名称（对应skills下的文件夹名称），
            值为该类别下的所有工具模块名称列表（.py文件名，不包括__开头的文件）。

    Example:
        >>> skills = list_skills()
        >>> skills['math']
        ['basic.py']
    """
    skills_path: Path = __get_skills_path()

    tools_dict: dict[Any, Any] = {}

    if not skills_path.exists():
        return tools_dict.__str__()

    # 遍历skills目录
    for category_path in skills_path.iterdir():
        # 只处理目录
        if not category_path.is_dir():
            continue

        # 获取该目录下所有.py文件
        md_files: list[Any] = []
            # print(category_path)
        md_files = list(category_path.glob("introduction.md"))
        if len(md_files) > 0:
            tools_dict[category_path.name] = md_files[0].read_text()

    return tools_dict.__str__()

def get_skills_desc(skill_type:str)-> str:
    skills_path: Path = __get_skills_path()
    skill_path = skills_path / skill_type / 'skills.md'
    if skill_path.exists():
        return skill_path.read_text()
        
    return "Skill not found"    

def get_skill_details(skill_type: str, skill_names: list[dict[str, list[str]]]) -> str:
    """获取指定技能的详细信息。

    Args:
        skill_type: 技能类型/类别名称。
        skill_names: 技能文件名列表，每个元素是一个字典，包含文件名和函数名列表。

    Returns:
        str: 包含导入路径和选中函数源代码的字符串，如果技能不存在返回"Skill not found"。
    """
    skills_path: Path = __get_skills_path()
    skill_path = skills_path / skill_type / 'scripts'
    
    # 获取src目录路径，用于计算导入路径
    src_path = Path(__file__).resolve().parent.parent.parent
    
    all_import_statements = []
    all_imports = []
    all_functions = []
    seen_imports = set()
    
    for skill_name_dict in skill_names:
        # 获取文件名和函数名列表
        file_name = list(skill_name_dict.keys())[0]
        func_names = list(skill_name_dict.values())[0]
        
        # 构建完整文件路径
        file_path = skill_path / file_name
        
        if not file_path.exists():
            continue
        
        # 计算导入路径
        try:
            # 获取相对于src目录的路径
            relative_path = file_path.relative_to(src_path)
            # 转换为模块路径（去掉.py扩展名，用.替换/）
            # 使用src.前缀，因为项目根目录会被添加到sys.path
            module_path = str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')
            module_path = 'src.' + module_path
            # 生成导入语句
            import_statement = f"# 如果使用该函数，这是该函数的导入路径\nfrom {module_path} import {', '.join(func_names)}"
            all_import_statements.append(import_statement)
        except ValueError:
            # 如果无法计算相对路径，跳过
            continue
            
        # 读取文件内容
        source_code = file_path.read_text()
        
        # 解析AST
        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError:
            continue
        
        # 收集所有导入语句
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_source = ast.get_source_segment(source_code, node)
                if import_source and import_source not in seen_imports:
                    all_imports.append(import_source)
                    seen_imports.add(import_source)
        
        # 提取选中的函数（保持原始顺序）
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in func_names:
                # 获取函数的源代码
                func_source = ast.get_source_segment(source_code, node)
                if func_source:
                    all_functions.append(func_source)
    
    # 组合导入语句、文件导入和函数
    result_parts = []
    
    # 首先添加导入路径语句
    if all_import_statements:
        result_parts.extend(all_import_statements)
    
    # 然后添加文件中的导入语句
    if all_imports:
        result_parts.extend(all_imports)
    
    # 最后添加函数代码
    if all_functions:
        result_parts.extend(all_functions)
    
    if result_parts:
        return "\n\n".join(result_parts)
    
    return "Skill not found"
    # if skill_type in skills_dict and skill_name in skills_dict[skill_type]:
    #     skill_path: Path = __get_skills_path() / skill_type / skill_name
    #     if skill_path.exists():
    #         return skill_path.read_text()
    # return "Skill not found"


SKILL_DICT: dict[str, Callable] = {
    "list_skills": list_skills,
    "get_skills_desc": get_skills_desc,
    "get_skill_details": get_skill_details,
    "get_skill_root": get_skill_root,
    "list_skill_files": list_skill_files,
    "read_skill_file": read_skill_file,
}


if __name__ == "__main__":
    # skill_dict = get_skill_details("math", "basic.py")
    # print(skill_dict)

    # skill_dict = list_skills()
    # print(skill_dict)
    # r = get_skills_desc('math')
    # print(r)
    skill_names = [{'basic.py': ['add','multiply','subtract']}]
    r = get_skill_details('math', skill_names)
    print(r)

