"""路径工具

提供统一的路径管理功能:
- 项目根目录解析
- 子目录创建
- 路径规范化
- 文件搜索

Usage:
    >>> from quantcli.utils import project_root, data_dir, ensure_dir
    >>> root = project_root()
    >>> data = data_dir()
"""

import os
import glob
from pathlib import Path
from typing import List, Optional, Union


# 项目根目录 (向上查找标记文件)
ROOT_MARKERS = [".git", "pyproject.toml", "quantcli", "CLAUDE.md"]


def find_project_root(start: Optional[Path] = None) -> Path:
    """查找项目根目录

    从 start 目录向上查找，找到包含标记文件的目录为止。

    Args:
        start: 起始路径，None=当前工作目录

    Returns:
        项目根目录 Path
    """
    if start is None:
        start = Path.cwd()

    start = Path(start).resolve()
    current = start

    for _ in range(10):  # 最多向上查找10层
        for marker in ROOT_MARKERS:
            if (current / marker).exists():
                return current

        parent = current.parent
        if parent == current:  # 已到达根目录
            break
        current = parent

    # 默认返回当前目录
    return Path.cwd()


# 缓存项目根目录
_project_root: Optional[Path] = None


def project_root() -> Path:
    """获取项目根目录 (推荐使用此函数)"""
    global _project_root
    if _project_root is None:
        _project_root = find_project_root()
    return _project_root


def set_project_root(path: Union[str, Path]):
    """手动设置项目根目录"""
    global _project_root
    _project_root = Path(path).resolve()
    return _project_root


# =============================================================================
# 目录快捷方式
# =============================================================================

def data_dir(sub: str = "") -> Path:
    """数据目录

    Args:
        sub: 子目录名

    Returns:
        data/sub 路径
    """
    root = project_root()
    path = root / "data"
    if sub:
        path = path / sub
    return ensure_dir(path)


def raw_data_dir() -> Path:
    """原始数据目录 (data/raw)"""
    return data_dir("raw")


def cache_dir() -> Path:
    """缓存目录 (data/cache)"""
    return data_dir("cache")


def features_dir() -> Path:
    """特征数据目录 (data/features)"""
    return data_dir("features")


def factors_dir() -> Path:
    """因子定义目录 (factors)"""
    return ensure_dir(project_root() / "factors")


def builtin_factors_dir() -> Path:
    """内置因子目录 (quantcli/factors/)

    兼容可编辑安装模式。
    对于可编辑安装，包在 project_root/quantcli/ 目录下。
    对于标准安装，包在 site-packages/quantcli/ 目录下。

    Returns:
        内置因子目录 Path
    """
    root = project_root()
    cli_path = root / "quantcli"

    # 可编辑安装: quantcli 是项目子目录
    if cli_path.exists():
        return cli_path / "factors"

    # 标准安装: quantcli 在 site-packages
    import quantcli
    try:
        return Path(quantcli.__file__).parent / "factors"
    except (TypeError, AttributeError):
        return root / "factors"


def strategies_dir() -> Path:
    """策略文件目录 (strategies)"""
    return ensure_dir(project_root() / "strategies")


def results_dir(sub: str = "") -> Path:
    """结果目录 (results)

    Args:
        sub: 子目录名

    Returns:
        results/sub 路径
    """
    path = ensure_dir(project_root() / "results")
    if sub:
        path = path / sub
    return path


def logs_dir() -> Path:
    """日志目录 (logs)"""
    return ensure_dir(project_root() / "logs")


def tests_dir() -> Path:
    """测试目录 (tests)"""
    return ensure_dir(project_root() / "tests")


# =============================================================================
# 目录操作
# =============================================================================

def ensure_dir(path: Union[str, Path]) -> Path:
    """确保目录存在

    Args:
        path: 目录路径

    Returns:
        Path 对象
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_dir(path: Union[str, Path]) -> Path:
    """确保父目录存在

    Args:
        path: 文件路径

    Returns:
        Path 对象
    """
    path = Path(path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def clean_dir(path: Union[str, Path], pattern: Optional[str] = None) -> int:
    """清空目录

    Args:
        path: 目录路径
        pattern: 文件匹配模式，None=全部删除

    Returns:
        删除的文件数量
    """
    path = Path(path)
    count = 0

    if pattern:
        for f in path.glob(pattern):
            if f.is_file():
                f.unlink()
                count += 1
    else:
        for f in path.iterdir():
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                f.unlink(True)  # 递归删除
            count += 1

    return count


def copy_dir(src: Union[str, Path], dst: Union[str, Path]):
    """复制目录

    Args:
        src: 源目录
        dst: 目标目录
    """
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source directory not found: {src}")

    ensure_dir(dst)

    for item in src.iterdir():
        src_path = dst / item.name
        if item.is_dir():
            copy_dir(item, src_path)
        else:
            import shutil
            shutil.copy2(item, src_path)


def move_dir(src: Union[str, Path], dst: Union[str, Path]):
    """移动目录"""
    import shutil
    shutil.move(str(src), str(dst))


# =============================================================================
# 文件操作
# =============================================================================

def find_files(
    pattern: str,
    root: Optional[Path] = None,
    recursive: bool = True
) -> List[Path]:
    """查找文件

    Args:
        pattern: glob 模式
        root: 搜索根目录
        recursive: 是否递归

    Returns:
        匹配的文件列表
    """
    root = root or project_root()
    if recursive:
        return list(root.glob(f"**/{pattern}"))
    return list(root.glob(pattern))


def find_file(name: str, root: Optional[Path] = None) -> Optional[Path]:
    """查找单个文件

    Args:
        name: 文件名
        root: 搜索根目录

    Returns:
        文件路径，未找到返回 None
    """
    root = root or project_root()

    # 向上查找
    current = root
    for _ in range(10):
        found = current / name
        if found.exists():
            return found
        if current == current.parent:
            break
        current = current.parent

    return None


def file_age(path: Union[str, Path]) -> float:
    """获取文件年龄 (秒)

    Args:
        path: 文件路径

    Returns:
        文件创建时间距今的秒数
    """
    import time
    path = Path(path)
    if not path.exists():
        return float("inf")
    return time.time() - path.stat().st_ctime


def file_size(path: Union[str, Path]) -> int:
    """获取文件大小 (字节)"""
    return Path(path).stat().st_size


def format_size(size: int) -> str:
    """格式化文件大小

    Args:
        size: 字节数

    Returns:
        可读的大小字符串
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


# =============================================================================
# 路径工具
# =============================================================================

def normpath(path: Union[str, Path]) -> Path:
    """规范化路径"""
    return Path(os.path.normpath(path))


def abspath(path: Union[str, Path]) -> Path:
    """获取绝对路径"""
    return Path(path).resolve()


def relpath(path: Union[str, Path], start: Optional[Path] = None) -> Path:
    """获取相对路径

    Args:
        path: 文件路径
        start: 起始路径，默认项目根目录

    Returns:
        相对路径
    """
    start = start or project_root()
    return Path(os.path.relpath(path, start))


def same_path(a: Union[str, Path], b: Union[str, Path]) -> bool:
    """判断两个路径是否相同"""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except:
        return False


def is_subpath(path: Union[str, Path], parent: Union[str, Path]) -> bool:
    """判断 path 是否是 parent 的子路径"""
    path = Path(path).resolve()
    parent = Path(parent).resolve()
    return str(path).startswith(str(parent) + os.sep)


# =============================================================================
# 扩展名处理
# =============================================================================

def get_extension(path: Union[str, Path]) -> str:
    """获取文件扩展名 (含点)"""
    return Path(path).suffix


def without_extension(path: Union[str, Path]) -> str:
    """去除扩展名"""
    return str(Path(path).with_suffix(""))


def replace_extension(path: Union[str, Path], new_ext: str) -> Path:
    """替换扩展名"""
    path = Path(path)
    if not new_ext.startswith("."):
        new_ext = "." + new_ext
    return path.with_suffix(new_ext)


# =============================================================================
# 临时文件
# =============================================================================

def temp_dir(sub: str = "") -> Path:
    """获取临时目录

    Args:
        sub: 子目录名

    Returns:
        临时目录路径
    """
    import tempfile
    base = tempfile.gettempdir()
    path = Path(base) / "quantcli"
    if sub:
        path = path / sub
    return ensure_dir(path)


def temp_file(suffix: str = "") -> Path:
    """创建临时文件

    Args:
        suffix: 文件后缀

    Returns:
        临时文件路径
    """
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(path)
