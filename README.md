# doubao
dify-on-wechat/chatgpt-on-wechat插件，实现豆包生图，参考图编辑，区域重绘等功能

# 豆包插件
本项目所有代码及资料仅限技术交流，禁止用于生产环境或商业用途，如果觉得豆包使用不错有能力尽量多去支持购买官方API

## 简介
基于豆包页面端逆向的图片生成插件。支持绘画、上传参考图编辑、扩图、区域重绘、抠图功能。


## 功能特点
1. AI绘画：支持多风格和比例
2. 图片放大：支持查看原图
3. 参考图编辑：上传图片对图片进行编辑
4. 抠图：上传图片进行抠出主体
5. 区域重绘：上传图片，圈选或者涂抹指定区域进行编辑
## 安装方法
1. 将插件文件夹复制到项目的plugins目录下
2. 复制config.json.template为config.json并填写配置
3. 安装依赖：pip install -r requirements.txt

## 配置说明
在config.json中配置以下参数：
1. video_api：API相关配置
   - cookie：cookie
   - sign：签名
   - msToken：token
   - a_bogus：验证参数
2. storage：存储相关配置
   - retention_days：数据保留天数

## 使用方法
1. 生成图片：豆包 [描述词] [风格] [比例]
2. 查看原图：$u [图片ID] [序号]
3. 扩图：$k [图片ID] [比例]
4. 编辑：$v [图片ID] [描述词]
5. 区域重绘：重绘 [描述词] ——上传图片——画笔圈选需要修改的区域

·重绘: 默认圈选模式，对圈选区域作为修改区域

·重绘 反选: 圈选区域为保留区域，圈选外区域作为修改区域

·涂抹：涂抹区域作为修改去区域

7. 抠图：抠图 上传图片抠出主体

## 示例
1. 豆包 一只汉服美女 人像摄影 2:3![TempDragFile_20250130_122242](https://github.com/user-attachments/assets/c776ebb0-8b92-41a6-858e-510a64a28b71)
2. $u 1704067890 2 ![Screenshot_2025_0130_122405](https://github.com/user-attachments/assets/f4c6c327-b112-47f1-8250-864b52d45d41)
3. $v 1704067890 2 戴个墨镜![Screenshot_2025_0130_122933](https://github.com/user-attachments/assets/3ba60b92-d613-4134-a632-0e5f73737ccd)

4. $k 1704067890 2 16:9![Screenshot_2025_0130_123054](https://github.com/user-attachments/assets/799bab49-c5aa-4ff6-9525-43a693005d05)

5. 抠图![Screenshot_2025_0130_122727](https://github.com/user-attachments/assets/c168e3eb-cd46-4dcc-a10f-4efe980550b9)
6. 参考图 换成二次元风格![Screenshot_2025_0130_124332](https://github.com/user-attachments/assets/203914e7-9b58-496e-8052-d851f7c435b2)


7. 重绘 反选 换成温馨室内![18839](https://github.com/user-attachments/assets/c90bc9bd-9c64-47ff-9a37-75d3feeff192)

## 更新
2025/2/8：重绘和重绘 反选功能，支持多种颜色圈选区域作为修改或者保留区域，可以自主根据图片色彩选用其他颜色标记，理论上可以避免之前只能识别红色信息，红色圈选会被原图色彩信息干扰

## 计划更新
1.修复参考图和重绘等功能编辑图片后，重新生成指令失效问题

2.或使用APP接口支持英文提示词绘图（感觉APP生成图片质量比页面端好一些，可能错觉）

3.kimi最近对话总是会因为使用人数多，不能获取回复，可能使用豆包进行识别图片或者链接总结

4.换背景，自动识别主体区域保留更换背景

![20814](https://github.com/user-attachments/assets/e5af6218-8582-4692-bb4d-aa4e3dbd62f2)



5.换主体，和换背景相反只修改主体

![20820](https://github.com/user-attachments/assets/4aec76de-3a08-42e9-90b6-711275076657)



