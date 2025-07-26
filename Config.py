import os
import yaml

import sys


# 获取配置文件目录（兼容打包后环境）
def get_base_dir():
    if getattr(sys, 'frozen', False):
        # 打包后环境（可执行文件所在目录）
        return os.path.dirname(sys.executable)
    else:
        # 源码环境（当前文件所在目录）
        return os.path.dirname(__file__)


# 配置文件路径
CONFIG_PATH = os.path.join(get_base_dir(), "config.yml")
BASE_DOWNLOAD_DIR = os.path.join(get_base_dir(), "downloads")
# 默认配置
DEFAULT_CONFIG = {
    'base_download_dir': BASE_DOWNLOAD_DIR,
    'ffmpeg': {'path': ''},
    'overwrite_strategy': {
        'overwrite_existing': False,
        'higher_quality_replace': True
    },
    'sessdata': ""
}


def load_config():
    """
    加载配置文件，如果不存在则创建默认配置

    Returns:
        dict: 配置字典
    """
    if not os.path.exists(CONFIG_PATH):
        print("配置文件config.yml不存在，将创建新文件并使用默认配置")
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True)
        return DEFAULT_CONFIG
    else:
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            config_updated = False
            # 确保配置文件包含所有必要的键
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
                    print(f"配置文件缺少'{key}'配置，已添加默认值")
                    config_updated = True
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in config[key]:
                            config[key][sub_key] = sub_value
                            print(f"配置文件缺少'{key}.{sub_key}'配置，已添加默认值")
                            config_updated = True

            # 处理旧版本配置中可能存在的download_dir
            if 'download_dir' in config and 'base_download_dir' not in config:
                config['base_download_dir'] = config['download_dir']
                del config['download_dir']
                config_updated = True
                print("已更新下载目录配置为base_download_dir")

            if config_updated:
                save_config(config)
                print("配置文件已更新")

            return config

        except Exception as e:
            print(f"读取配置文件失败: {e}，将使用默认配置")
            return DEFAULT_CONFIG


def save_config(config):
    """
    保存配置到文件

    Args:
        config (dict): 配置字典
    """
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
    except Exception as e:
        print(f"保存配置文件失败: {e}")
