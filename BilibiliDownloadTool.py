import argparse

from BilibiliDownloader import BilibiliDownloader


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='B站视频下载工具')
    parser.add_argument('-link', '--link', '-l', '--l', type=str, required=True, help='视频的BV号、AV号或完整链接')

    args = parser.parse_args()

    try:
        # 创建下载器实例并执行下载
        downloader = BilibiliDownloader(args.link)
        downloader.run()
    except Exception as e:
        print(f"下载失败: {str(e)}")


if __name__ == "__main__":
    main()
