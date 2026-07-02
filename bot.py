import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

# 关键：从 plugins 文件夹中加载所有插件
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()