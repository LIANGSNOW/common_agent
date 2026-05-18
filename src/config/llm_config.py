from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 加载 .env 文件
load_dotenv()


class LLMSettings(BaseSettings):
    """LLM 配置设置"""

    class Config:
        env_file: str = ".env"
        env_file_encoding: str = "utf-8"
        extra: str = "ignore"
        env_prefix: str = "llm_"

    model_name: str
    api_key: str
    base_url: str
    temperature: float = 0.7  # 默认值


# 创建全局配置实例
settings: LLMSettings = LLMSettings()  # type: ignore
