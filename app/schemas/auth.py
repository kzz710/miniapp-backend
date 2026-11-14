"""登录与用户相关模型。"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, description="uni.login 返回的 code")
    # 缺省或空字符串由服务层按 weixin 处理，非法值返回 400（不用枚举以免变成 422）
    platform: str | None = Field(
        default=None,
        max_length=32,
        description="登录平台：weixin / toutiao / kuaishou / baidu，缺省为 weixin",
    )


class H5LoginRequest(BaseModel):
    """H5 端匿名登录：由浏览器本地生成的稳定设备标识。"""

    device_id: str = Field(
        ...,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="设备标识（8~64 位字母数字、下划线或短横线）",
    )


class UserOut(BaseModel):
    user_id: str = Field(..., description="对外用户 ID，如 U10001")
    username: str
    avatar_text: str
    avatar_color: str
    created_at: str | None = None


class LoginResponse(BaseModel):
    token: str
    expires_in: int
    user: UserOut


class UserUpdate(BaseModel):
    # 长度与字符集统一交给 auth_service.validate_username 校验，便于返回中文提示
    username: str = Field(..., min_length=1, max_length=32, description="新用户名（2~16 字符）")
