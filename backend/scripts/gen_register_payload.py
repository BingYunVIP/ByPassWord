"""生成一份可直接粘贴到 Swagger / curl 的注册请求体。

用法（在 backend 目录）：
    .venv/bin/python scripts/gen_register_payload.py [email]

会打印合法 base64 的 kdf/authHash/wrappedDek/dekNonce，避免手填被 400 拦住。
"""

import base64
import json
import os
import sys


def b64(n: int) -> str:
    return base64.b64encode(os.urandom(n)).decode("ascii")


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else f"demo-{os.urandom(3).hex()}@example.com"
    payload = {
        "email": email,
        "kdf": {
            "algo": "argon2id",
            "salt": b64(16),
            "memoryKib": 65536,
            "time": 3,
            "parallel": 1,
        },
        "authHash": b64(32),
        "wrappedDek": b64(48),
        "dekNonce": b64(12),
        "recoveryWrappedDek": b64(48),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n# 邮箱: {email}")
    print("# 注意：authHash 是「客户端派生值」的占位，真实前端会用主密码算出它；")
    print("#       这里仅为接口联调，登录时请使用同一份 authHash。")


if __name__ == "__main__":
    main()
