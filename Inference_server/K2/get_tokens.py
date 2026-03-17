#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Improved K2Think Token Extractor
Handles Brotli compression and extracts tokens from Set-Cookie headers
"""

import os
import sys
import requests
import json
import time
import re
from typing import Optional, List, Dict
from dotenv import load_dotenv

# Ensure UTF-8 output
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Load environment variables
load_dotenv()


class K2ThinkTokenExtractor:
    def __init__(self):
        self.base_url = "https://www.k2think.ai"
        self.login_url = f"{self.base_url}/api/v1/auths/signin"

        # Check for proxy configuration
        proxy_url = os.getenv("PROXY_URL", "")
        self.proxies = {}
        if proxy_url:
            self.proxies = {'http': proxy_url, 'https': proxy_url}
            print(f"使用代理: {proxy_url}")
        else:
            print("未配置代理，直接连接")

        # Updated headers to match working test
        self.headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Content-Type': 'application/json',
            'Origin': 'https://www.k2think.ai',
            'Referer': 'https://www.k2think.ai/auth?mode=signin',
            'Sec-Ch-Ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
        }

    def extract_token_from_cookie_header(self, set_cookie_header: str) -> Optional[str]:
        """
        Extract token from Set-Cookie header string
        Handles multiple cookies in one header
        """
        if not set_cookie_header:
            return None

        # Split by comma followed by space and a new cookie name
        # But be careful not to split on commas within cookie attributes
        cookies = []
        current_cookie = ""

        for part in set_cookie_header.split(','):
            part = part.strip()
            # Check if this looks like the start of a new cookie (has '=')
            if '=' in part and not part.startswith((' ', '\t')):
                if current_cookie:
                    cookies.append(current_cookie)
                current_cookie = part
            else:
                current_cookie += ',' + part

        if current_cookie:
            cookies.append(current_cookie)

        # Look for token in any of the cookies
        for cookie in cookies:
            if 'token=' in cookie:
                match = re.search(r'token=([^;,\s]+)', cookie)
                if match:
                    return match.group(1)

        return None

    def login_and_get_token(self, email: str, password: str, retry_count: int = 3) -> Optional[str]:
        """
        Login and extract token from Set-Cookie header
        """
        login_data = {
            "email": email,
            "password": password
        }

        for attempt in range(retry_count):
            try:
                # Create a new session
                session = requests.Session()

                # Make the request
                response = session.post(
                    self.login_url,
                    json=login_data,
                    headers=self.headers,
                    proxies=self.proxies if self.proxies else None,
                    timeout=30,
                    allow_redirects=False
                )

                # Check if login was successful
                if response.status_code == 200:
                    # Extract token from Set-Cookie header
                    if 'Set-Cookie' in response.headers:
                        set_cookie = response.headers['Set-Cookie']
                        token = self.extract_token_from_cookie_header(set_cookie)

                        if token:
                            # Validate token (JWT should have 3 parts separated by dots)
                            if token.count('.') == 2:
                                return token
                            else:
                                print(f"⚠️  警告: 提取的token格式不正确: {token[:30]}...")
                        else:
                            print("⚠️  警告: Set-Cookie中未找到token")
                    else:
                        print("⚠️  警告: 响应中没有Set-Cookie头")

                    # Also check cookies from session
                    for cookie in session.cookies:
                        if cookie.name == 'token':
                            if cookie.value.count('.') == 2:
                                return cookie.value

                elif response.status_code == 401:
                    print(f"❌ 登录失败: 401 Unauthorized (账号或密码错误)")
                    return None
                elif response.status_code >= 400:
                    print(f"❌ 登录失败: HTTP {response.status_code}")
                    return None

            except requests.exceptions.Timeout:
                print(f"⚠️  尝试 {attempt + 1}/{retry_count}: 请求超时")
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
            except Exception as e:
                print(f"⚠️  尝试 {attempt + 1}/{retry_count}: {str(e)}")
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue

        return None

    def load_accounts(self, file_path: str = "./accounts.txt") -> List[Dict[str, str]]:
        """Load accounts from JSON file"""
        accounts = []

        if not os.path.exists(file_path):
            print(f"❌ 账户文件不存在: {file_path}")
            return accounts

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

                # Try to parse as JSON
                try:
                    account_data = json.loads(content)

                    # Validate required fields
                    if 'email' in account_data and 'password' in account_data:
                        accounts.append({
                            'email': account_data['email'],
                            'password': account_data['password']
                        })
                    else:
                        print(f"⚠️  账户配置缺少必需字段")

                except json.JSONDecodeError:
                    print(f"⚠️  无法解析accounts.txt为JSON格式")

        except Exception as e:
            print(f"❌ 读取账户文件失败: {e}")

        return accounts

    def save_tokens(self, tokens: List[str], file_path: str = "./data/tokens.txt"):
        """Save tokens to file, one per line"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# K2Think tokens - auto-generated\n")
                for token in tokens:
                    f.write(token + '\n')

            print(f"✅ 成功保存 {len(tokens)} 个token到: {file_path}")
            return True

        except Exception as e:
            print(f"❌ 保存tokens失败: {e}")
            return False

    def process_all_accounts(self, accounts_file: str = "./accounts.txt",
                           tokens_file: str = "./data/tokens.txt") -> bool:
        """Process all accounts and save tokens"""
        print("\n" + "=" * 70)
        print("🔑 K2Think Token Extractor (Improved)")
        print("=" * 70)
        print()

        # Load accounts
        accounts = self.load_accounts(accounts_file)

        if not accounts:
            print("❌ 没有找到有效的账户配置")
            return False

        print(f"📋 找到 {len(accounts)} 个账户")
        print()

        # Process each account
        tokens = []
        success_count = 0
        failed_count = 0

        for i, account in enumerate(accounts, 1):
            email = account['email']
            password = account['password']

            print(f"[{i}/{len(accounts)}] 处理账户: {email}")

            token = self.login_and_get_token(email, password)

            if token:
                tokens.append(token)
                success_count += 1
                print(f"✅ 成功获取token: {token[:50]}...")
            else:
                failed_count += 1
                print(f"❌ 获取token失败")

            print()

        # Save tokens
        print("=" * 70)
        print(f"📊 处理结果: 成功 {success_count}, 失败 {failed_count}")
        print("=" * 70)
        print()

        if tokens:
            if self.save_tokens(tokens, tokens_file):
                print(f"✅ Tokens已保存到: {tokens_file}")
                print()
                return True
        else:
            print("❌ 没有成功获取任何token")
            print()

        return False


def main():
    import sys

    # Default file paths
    accounts_file = "./data/accounts.txt"
    tokens_file = "./data/tokens.txt"

    # Check for command line arguments
    if len(sys.argv) > 1:
        accounts_file = sys.argv[1]
    if len(sys.argv) > 2:
        tokens_file = sys.argv[2]

    # Create extractor and process
    extractor = K2ThinkTokenExtractor()
    success = extractor.process_all_accounts(accounts_file, tokens_file)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()