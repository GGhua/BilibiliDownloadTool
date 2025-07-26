import json
import os
import re
import subprocess
from shutil import which

import requests
from Crypto.Cipher import AES
from lxml import etree
from tqdm import tqdm

from Config import load_config, save_config, get_base_dir

DEFAULT_QUALITY_PRIORITY = {
    126: 9,  # 8K 超高清
    125: 8,  # HDR 真彩
    120: 7,  # 4K 超清
    116: 6,  # 1080P60 高码率
    112: 5,  # 1080P 高码率
    80: 4,  # 1080P 高清
    74: 3,  # 720P 高码率
    64: 2,  # 720P 准高清
    32: 1,  # 480P 清晰
    16: 0  # 360P 流畅
}

DEFAULT_QUALITY_MAP = {
    16: "360P 流畅",
    32: "480P 清晰",
    64: "720P 准高清",
    74: "720P 高码率",
    80: "1080P 高清",
    112: "1080P 高码率",
    116: "1080P60 高码率",
    120: "4K 超清",
    125: "HDR 真彩",
    126: "8K 超高清"
}


class BilibiliDownloader:
    """
    B站视频下载器类
    支持下载B站视频，包括DASH和FLV格式
    """

    def __init__(self, video_url, cookie_path=None):
        """
        初始化下载器

        Args:
            video_url (str): 视频的AV号、BV号或完整链接
            cookie_path (str, optional): Cookie文件路径
        """
        # 加载配置
        self.config = load_config()

        # 提取并初始化视频URL
        self.av_num = self._extract_av_bv(video_url.strip())
        self.url = f'https://www.bilibili.com/video/{self.av_num}'

        # 初始化请求会话
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.session.headers.update(self.headers)

        # 登录状态相关
        self.logged_in = False
        self.sessdata = ""
        self.load_cookies(cookie_path)

        # 提取配置项
        self.base_download_dir = os.path.join(get_base_dir(), self.config['base_download_dir'])
        print(self.base_download_dir)
        self.ffmpeg_path = self.config['ffmpeg']['path']
        self.quality_priority = self.config.get('quality_priority', DEFAULT_QUALITY_PRIORITY)
        self.quality_map = self.config.get('quality_map', DEFAULT_QUALITY_MAP)
        self.overwrite_existing = self.config['overwrite_strategy']['overwrite_existing']
        self.higher_quality_replace = self.config['overwrite_strategy']['higher_quality_replace']

        # 创建基础下载目录
        os.makedirs(self.base_download_dir, exist_ok=True)

        # 验证FFmpeg（必须在设置ffmpeg_path之后调用）
        self._verify_ffmpeg()

        # 获取网页响应
        try:
            self.html_response = self.session.get(self.url, timeout=10)
            self.html_response.raise_for_status()
            self.html_tree = etree.HTML(self.html_response.text)
        except Exception as e:
            print(f"获取视频页面失败: {e}")
            self.html_response = None
            self.html_tree = None

    def _extract_av_bv(self, video_url):
        """
        从输入字符串中提取AV号或BV号

        Args:
            video_url (str): 可能包含AV号、BV号或完整链接的字符串

        Returns:
            str: 提取到的AV号或BV号

        Raises:
            ValueError: 当无法提取到有效的AV号或BV号时
        """
        # 如果输入是完整的URL，从中提取AV/BV号
        match = re.search(r'(av\d+|BV[0-9A-Za-z]+)', video_url)
        if match:
            return match.group(1)
        else:
            # 如果输入本身就是AV/BV号
            if re.match(r'^(av\d+|BV[0-9A-Za-z]+)$', video_url):
                return video_url
            else:
                raise ValueError("无法从输入中提取有效的AV号或BV号")

    def save_config(self):
        """
        保存配置到文件
        """
        save_config(self.config)

    def _verify_ffmpeg(self):
        """
        验证FFmpeg是否可用
        """
        try:
            exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            ffmpeg_exe = os.path.join(self.ffmpeg_path, exe_name) if self.ffmpeg_path else exe_name

            if not which(ffmpeg_exe) and not os.path.exists(ffmpeg_exe):
                raise Exception(f"FFmpeg文件不存在: {ffmpeg_exe}")

            result = subprocess.run(
                [ffmpeg_exe, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg运行失败: {result.stderr}")

            print(f"已找到FFmpeg: {ffmpeg_exe}")
            return True

        except Exception as e:
            print(f"FFmpeg验证失败: {e}")
            print("请检查FFmpeg路径是否正确，或重新安装FFmpeg")
            self._auto_config_ffmpeg()
            return False

    def _auto_config_ffmpeg(self):
        """
        自动配置FFmpeg路径
        """
        system_ffmpeg = which('ffmpeg') or which('ffmpeg.exe')
        if system_ffmpeg and os.path.exists(system_ffmpeg):
            ffmpeg_bin_dir = os.path.dirname(system_ffmpeg)
            print(f"自动找到了FFmpeg bin目录: {ffmpeg_bin_dir}")
            self.ffmpeg_path = ffmpeg_bin_dir
            self.config['ffmpeg']['path'] = ffmpeg_bin_dir
            self.save_config()
        else:
            print("未找到FFmpeg的bin目录，请手动配置")
            while True:
                user_input = input("请手动输入FFmpeg的bin目录完整路径: ").strip()
                exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
                if user_input and os.path.exists(os.path.join(user_input, exe_name)):
                    self.ffmpeg_path = user_input
                    print(f"已使用手动输入的FFmpeg bin目录: {self.ffmpeg_path}")
                    self.config['ffmpeg']['path'] = user_input
                    self.save_config()
                    break
                else:
                    print("输入的目录无效或不包含FFmpeg可执行文件，请重新输入")

    def load_cookies(self, cookie_path=None):
        """
        加载Cookie，以sessdata为主

        Args:
            cookie_path (str, optional): Cookie文件路径
        """
        # 从配置文件加载sessdata
        self.sessdata = self.config.get('sessdata', '').strip()

        # 设置会话Cookie
        if self.sessdata:
            self.session.cookies.set('SESSDATA', self.sessdata)
            print("已从配置文件加载SESSDATA")

        # 检查登录状态
        self._check_login_status()

        # 如果未登录，提示用户输入
        if not self.logged_in:
            print("未检测到有效登录状态，更高画质可能无法下载")
            use_login = input("是否要使用登录状态下载？(y/n): ").strip().lower()
            if use_login == 'y':
                print("请在浏览器中登录B站后，获取SESSDATA")
                print("获取方法：F12打开开发者工具 -> Application -> Cookies -> .bilibili.com -> SESSDATA")
                self.sessdata = input("请输入SESSDATA值: ").strip()
                if self.sessdata:
                    self.session.cookies.set('SESSDATA', self.sessdata)
                    # 验证登录状态
                    if self._check_login_status():
                        # 保存到配置文件
                        save_sess = input("是否保存SESSDATA到配置文件？(y/n): ").strip().lower()
                        if save_sess == 'y':
                            self.config['sessdata'] = self.sessdata
                            self.save_config()
                            print("SESSDATA已保存到配置文件")
                else:
                    print("未输入有效的SESSDATA，将使用未登录状态")

    def _check_login_status(self):
        """
        检查登录状态

        Returns:
            bool: 是否已登录
        """
        try:
            url = "https://api.bilibili.com/x/web-interface/nav"
            response = self.session.get(url, timeout=10)
            data = response.json()

            if data["code"] == 0 and data["data"]["isLogin"]:
                self.logged_in = True
                print(f"登录状态有效，当前用户: {data['data']['uname']}")
                return True
            else:
                print("SESSDATA已过期或无效")
                self.logged_in = False
                return False
        except Exception as e:
            print(f"检查登录状态失败: {e}")
            self.logged_in = False
            return False

    def get_video_info(self):
        """
        获取视频信息

        Returns:
            tuple: (标题, CID, UP主名称, UP主ID)
        """
        if self.html_response is None or self.html_response.status_code != 200 or self.html_tree is None:
            return None, None, None, None

        html = self.html_response.text
        title = None
        cid = None
        up_name = None
        up_id = None

        # 提取视频标题
        xpath_queries = [
            '//h1[@class="video-title"]/@title',
            '//h1[@class="video-title"]/text()',
            '//meta[@property="og:title"]/@content',
            '//title/text()'
        ]

        for query in xpath_queries:
            title_elements = self.html_tree.xpath(query)
            if title_elements and len(title_elements) > 0:
                title = title_elements[0].strip()
                title = re.sub(r'_哔哩哔哩.*', '', title)
                title = re.sub(r'【.*?】', '', title)
                title = re.sub(r'\|.*', '', title)
                break

        # 提取cid
        cid_patterns = [
            r'"cid":(\d+),',
            r'cid=(\d+)',
            r'{"cid":(\d+)}'
        ]

        for pattern in cid_patterns:
            cid_match = re.search(pattern, html)
            if cid_match:
                cid = cid_match.group(1)
                break

        # 提取UP主信息
        up_info_pattern = r'window\.__INITIAL_STATE__=(.*?);\(function\(\)'
        up_info_match = re.search(up_info_pattern, html)
        if up_info_match:
            try:
                initial_state = json.loads(up_info_match.group(1))
                if 'upData' in initial_state:
                    up_name = initial_state['upData'].get('name', up_name)
                    up_id = initial_state['upData'].get('mid', up_id)
                elif 'videoData' in initial_state and 'owner' in initial_state['videoData']:
                    up_name = initial_state['videoData']['owner'].get('name', up_name)
                    up_id = initial_state['videoData']['owner'].get('mid', up_id)
            except:
                pass

        # 提取UP主名称 - 备用模式
        if not up_name:
            up_name_elements = self.html_tree.xpath('//a[@class="up-name"]/text()')
            if up_name_elements and len(up_name_elements) > 0:
                up_name = up_name_elements[0].strip()
            else:
                up_name_elements = self.html_tree.xpath('//meta[@name="author"]/@content')
                if up_name_elements and len(up_name_elements) > 0:
                    up_name = up_name_elements[0].strip()

        # 提取UP主ID - 备用模式
        if not up_id:
            up_id_patterns = [
                r'data-user-id="(\d+)"',
                r'up_uid=(\d+)',
                r'data-mid="(\d+)"'
            ]
            for pattern in up_id_patterns:
                up_id_match = re.search(pattern, html)
                if up_id_match:
                    up_id = up_id_match.group(1).strip()
                    break

        # 最终 fallback
        title = title if title else f"视频_{self.av_num}"
        up_name = up_name if up_name else "未知UP主"
        up_id = up_id if up_id else "unknown_id"

        return title, cid, up_name, up_id

    def get_best_quality(self, cid):
        """
        获取最佳可用画质

        Args:
            cid (str): 视频CID

        Returns:
            int: 最佳画质代码
        """
        # 按优先级排序的qn值列表
        quality_priority = sorted(
            self.quality_priority.keys(),
            key=lambda x: self.quality_priority[x],
            reverse=True
        )

        # 检查每个质量是否可用
        for qn in quality_priority:
            try:
                # 构建API请求
                if self.av_num.startswith('av'):
                    url = "https://api.bilibili.com/x/player/playurl"
                    params = {
                        "avid": self.av_num[2:],
                        "cid": cid,
                        "qn": qn,
                        "otype": "json",
                        "fnval": 16,
                        "fourk": 1 if qn in [120, 126, 127] else 0
                    }
                else:
                    url = "https://api.bilibili.com/x/player/playurl"
                    params = {
                        "bvid": self.av_num,
                        "cid": cid,
                        "qn": qn,
                        "otype": "json",
                        "fnval": 16,
                        "fourk": 1 if qn in [120, 126, 127] else 0
                    }

                response = self.session.get(url, params=params, timeout=10)
                data = response.json()

                if data["code"] == 0:
                    return qn
            except:
                continue

        # 默认返回1080P
        return 80

    def get_download_url(self, cid):
        """
        获取下载链接

        Args:
            cid (str): 视频CID

        Returns:
            dict: 下载信息字典
        """
        # 获取最佳可用质量
        best_qn = self.get_best_quality(cid)
        print(f"已选择最高可用清晰度: {self.quality_map.get(best_qn, f'未知({best_qn})')}")

        # 构建请求参数
        if self.av_num.startswith('av'):
            url = "https://api.bilibili.com/x/player/playurl"
            params = {
                "avid": self.av_num[2:],
                "cid": cid,
                "qn": best_qn,
                "otype": "json",
                "fnval": 16,
                "fourk": 1 if best_qn in [120, 126, 127] else 0,
                "fnver": 0
            }
        else:
            url = "https://api.bilibili.com/x/player/playurl"
            params = {
                "bvid": self.av_num,
                "cid": cid,
                "qn": best_qn,
                "otype": "json",
                "fnval": 16,
                "fourk": 1 if best_qn in [120, 126, 127] else 0,
                "fnver": 0
            }

        try:
            response = self.session.get(url, params=params, timeout=10)
            data = response.json()

            if data["code"] != 0:
                error_msg = f"获取下载链接失败: {data['message']}"
                if data["code"] == -101:
                    error_msg += "\n需要登录才能下载此视频，请确保已输入有效的SESSDATA"
                    if not self.logged_in:
                        error_msg += "\n建议重新输入SESSDATA后重试"
                elif data["code"] == -403:
                    error_msg += "\n权限不足，可能需要会员才能下载此清晰度"
                raise Exception(error_msg)

            if "dash" in data["data"]:
                return {
                    "type": "dash",
                    "video": data["data"]["dash"]["video"],
                    "audio": data["data"]["dash"]["audio"],
                    "quality": best_qn,
                    "quality_description": self.quality_map.get(best_qn, f'未知({best_qn})')
                }
            elif "durl" in data["data"]:
                return {
                    "type": "flv",
                    "durl": data["data"]["durl"],
                    "quality": best_qn,
                    "quality_description": self.quality_map.get(best_qn, f'未知({best_qn})'),
                    "format_name": data["data"]["format"]
                }
            else:
                raise Exception("API未返回有效下载链接，该视频可能受版权保护")

        except Exception as e:
            raise Exception(f"获取下载链接出错: {str(e)}")

    def get_existing_quality(self, directory, title, av_num):
        """
        检查已存在的视频质量

        Args:
            directory (str): 目录路径
            title (str): 视频标题
            av_num (str): 视频AV/BV号

        Returns:
            int or None: 已存在的视频质量代码，如果不存在则返回None
        """
        if not os.path.exists(directory):
            return None

        # 构建文件名模式，包含标题和av/bv号
        safe_title = re.sub(r'[\/:*?"<>|]', '', title)
        file_pattern = re.compile(re.escape(safe_title) + r'.+?' + re.escape(av_num) + r'\.mp4$')

        for filename in os.listdir(directory):
            if file_pattern.match(filename):
                for q_id, q_name in self.quality_map.items():
                    if str(q_name).split()[0] in filename:
                        return q_id
        return None

    def download_with_progress(self, url, filename, total_size=None, is_encrypted=False, key=None):
        """
        带进度条的下载函数

        Args:
            url (str): 下载链接
            filename (str): 保存文件名
            total_size (int, optional): 文件总大小
            is_encrypted (bool): 是否加密
            key (bytes): 解密密钥

        Returns:
            bool: 是否下载成功
        """
        temp_path = filename + ".part"
        start_pos = 0

        # 检查是否已存在完整文件
        if os.path.exists(filename):
            print(f"文件已存在: {os.path.basename(filename)}，跳过下载")
            return True

        # 检查是否有临时文件
        if os.path.exists(temp_path):
            start_pos = os.path.getsize(temp_path)
            if total_size and start_pos >= total_size:
                os.rename(temp_path, filename)
                return True

        headers = {
            "Range": f"bytes={start_pos}-",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com"
        }

        try:
            with self.session.get(url, headers=headers, stream=True, timeout=10) as response:
                response.raise_for_status()

                if not total_size:
                    total_size = int(response.headers.get("Content-Length", 0))
                total_size += start_pos

                mode = 'ab' if start_pos > 0 else 'wb'
                with open(temp_path, mode) as f, tqdm(
                        total=total_size,
                        initial=start_pos,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(filename)
                ) as pbar:

                    if is_encrypted and key:
                        cipher = AES.new(key, AES.MODE_CBC, iv=key)
                        for chunk in response.iter_content(chunk_size=1024 * 16):
                            if chunk:
                                decrypted_chunk = cipher.decrypt(chunk)
                                f.write(decrypted_chunk)
                                pbar.update(len(chunk))
                    else:
                        for chunk in response.iter_content(chunk_size=1024 * 16):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))

            os.rename(temp_path, filename)
            return True

        except Exception as e:
            print(f"下载失败: {str(e)}")
            if os.path.exists(temp_path) and os.path.getsize(temp_path) < 1024:
                os.remove(temp_path)
            return False

    def merge_video_audio(self, video_path, audio_path, output_path):
        """
        合并视频和音频

        Args:
            video_path (str): 视频文件路径
            audio_path (str): 音频文件路径
            output_path (str): 输出文件路径

        Returns:
            bool: 是否合并成功
        """
        if not self.ffmpeg_path:
            print("未配置有效的FFmpeg，无法合并视频音频")
            return False

        try:
            exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            ffmpeg_exe = os.path.join(self.ffmpeg_path, exe_name)

            if os.path.exists(output_path):
                os.remove(output_path)

            cmd = [
                ffmpeg_exe,
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-loglevel", "error",
                output_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg错误输出: {result.stderr}")

            # 清理临时文件
            if os.path.exists(video_path):
                os.remove(video_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)

            return True

        except Exception as e:
            print(f"合并音视频失败: {str(e)}")
            return False

    def run(self):
        """
        执行下载流程
        """
        try:
            # 获取视频信息
            title, cid, up_name, up_id = self.get_video_info()
            if not cid:
                print("无法获取视频CID，下载失败")
                return

            safe_title = re.sub(r'[\/:*?"<>|]', '', title)
            print(f"视频标题: {safe_title}, CID: {cid}, UP主: {up_name}({up_id})")

            # 检查是否需要登录
            if not self.logged_in:
                print("\n注意: 该视频可能需要登录才能下载高清版本")
                if input("是否现在输入SESSDATA? (y/n): ").lower() == 'y':
                    self.load_cookies()
                    if not self.logged_in:
                        print("登录失败，将尝试使用未登录状态继续")

            # 获取下载链接
            download_info = self.get_download_url(cid)
            if not download_info:
                print("无法获取下载链接，下载失败")
                return

            # 构建下载路径：基础目录/UP主名称_UP主ID/
            safe_up_name = re.sub(r'[\/:*?"<>|]', '_', up_name)
            self.video_dir = os.path.join(self.base_download_dir, f"{safe_up_name}_{up_id}")
            os.makedirs(self.video_dir, exist_ok=True)
            print(f"视频将保存到: {self.video_dir}")

            # 构建文件名：标题_清晰度_AV/BV号.mp4
            quality_desc = download_info['quality_description'].split()[0]
            output_filename = f"{safe_title}_{quality_desc}_{self.av_num}.mp4"
            output_path = os.path.join(self.video_dir, output_filename)

            # 检查现有文件
            existing_quality = self.get_existing_quality(self.video_dir, title, self.av_num)

            # 处理覆盖逻辑
            if existing_quality is not None:
                current_priority = self.quality_priority.get(download_info['quality'], 0)
                existing_priority = self.quality_priority.get(existing_quality, 0)

                if not self.overwrite_existing and not self.higher_quality_replace:
                    print(f"视频已存在: {output_filename}，跳过下载")
                    return
                elif self.higher_quality_replace and current_priority <= existing_priority:
                    print(f"已存在相同或更高质量的视频，跳过下载")
                    return
                elif self.overwrite_existing or (self.higher_quality_replace and current_priority > existing_priority):
                    print(f"将替换现有视频文件，质量: {quality_desc}")

            # 处理DASH格式（音视频分离）
            if download_info["type"] == "dash":
                print("检测到DASH格式视频（音视频分离）")

                # 选择最高质量的视频和音频流
                video_stream = max(download_info["video"],
                                   key=lambda x: (x.get("width", 0), x.get("height", 0), x.get("bandwidth", 0)))
                audio_stream = max(download_info["audio"],
                                   key=lambda x: x.get("bandwidth", 0))

                print(f"选中视频流: {video_stream['width']}x{video_stream['height']}")
                print(f"选中音频流: {audio_stream['bandwidth']}bps")

                # 临时文件路径
                video_path = os.path.join(self.video_dir, f"{safe_title}_video_{self.av_num}.m4s")
                audio_path = os.path.join(self.video_dir, f"{safe_title}_audio_{self.av_num}.m4s")

                # 下载视频流
                print("开始下载视频流...")
                if not self.download_file(video_stream["baseUrl"], video_path, video_stream.get("size")):
                    return

                # 下载音频流
                print("开始下载音频流...")
                if not self.download_file(audio_stream["baseUrl"], audio_path, audio_stream.get("size")):
                    return

                # 合并音视频
                print("开始合并音视频...")
                if self.merge_video_audio(video_path, audio_path, output_path):
                    print(f"下载完成: {output_path}")

            # 处理FLV格式（音视频合并）
            elif download_info["type"] == "flv":
                print("检测到FLV格式视频（音视频合并）")
                durl = download_info["durl"][0]

                # 检查文件是否已存在
                if os.path.exists(output_path):
                    print(f"视频文件已存在: {output_path}，跳过下载")
                    return

                print("开始下载视频...")
                if self.download_file(durl["url"], output_path, durl["length"]):
                    print(f"下载完成: {output_path}")

        except Exception as e:
            print(f"操作失败: {e}")

    def download_file(self, url, save_path, total_size=None):
        """
        下载文件的包装方法

        Args:
            url (str): 下载链接
            save_path (str): 保存路径
            total_size (int, optional): 文件总大小

        Returns:
            bool: 是否下载成功
        """
        return self.download_with_progress(url, save_path, total_size)


if __name__ == "__main__":
    video_url = input("请输入B站视频URL或AV/BV号: ")
    try:
        downloader = BilibiliDownloader(video_url)
        downloader.run()
    except ValueError as e:
        print(f"输入错误: {e}")
        exit(1)
