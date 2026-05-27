import logging
import random
import string
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_codes = {}

CODE_EXPIRE_SECONDS = 300
CODE_LENGTH = 6


def generate_code(target: str, code_type: str) -> str:
    key = f"{code_type}:{target}"
    code = "".join(random.choices(string.digits, k=CODE_LENGTH))
    _codes[key] = {"code": code, "expires_at": time.time() + CODE_EXPIRE_SECONDS}
    logger.info("验证码已生成: %s -> %s (类型: %s)", target, code, code_type)
    return code


def verify_code(target: str, code_type: str, code: str) -> Tuple[bool, str]:
    key = f"{code_type}:{target}"
    entry = _codes.get(key)
    if not entry:
        return False, "验证码不存在或已过期，请重新发送"
    if time.time() > entry["expires_at"]:
        del _codes[key]
        return False, "验证码已过期，请重新发送"
    if entry["code"] != code:
        return False, "验证码错误"
    del _codes[key]
    return True, "验证成功"


def send_sms_code(phone: str) -> Tuple[bool, str, Optional[str]]:
    if not phone or len(phone) < 7:
        return False, "手机号格式不正确", None
    code = generate_code(phone, "sms")
    logger.info("【模拟短信】手机号 %s 的验证码为: %s", phone, code)
    return True, "验证码已发送", code


def send_email_code(email: str) -> Tuple[bool, str, Optional[str]]:
    if not email or "@" not in email:
        return False, "邮箱格式不正确", None
    code = generate_code(email, "email")
    logger.info("【模拟邮件】邮箱 %s 的验证码为: %s", email, code)
    return True, "验证码已发送", code
