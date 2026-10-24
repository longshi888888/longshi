# 小隆公开合成数据演示

日期：2026-10-24；版本：0.6；状态：公开准备版，非正式企业系统。当前目录用于换机接续，**默认只加载仓库自带的虚构记录，不读取任何公司资料**。不接ERP、不调用大模型，没有真实经营统计、写入或外发能力。

## 直接运行

安装Python 3.10或更高版本。在本目录打开终端：

```powershell
python -B app.py
```

Windows有Edge时打开独立应用窗口；其他情况调用默认浏览器。问答演示只用Python标准库，不需要Node、显卡、模型权重或公司原件。`python -B -m unittest test_app -v`运行合成数据及本机服务边界检查。

可问：`查一下演示送货样本`、`查DEMO-A001`、`为什么有300和280两个金额？`、`这两笔送货已经到账了吗？`。页面所有样本值均是虚构数据，不是对真实原件做简单替名。

## 可选：恢复个人3D素材

没有素材时，页面明确显示“3D素材未配置”，问答仍然可用。公开仓库没有参考图片、生成GLB、截图、第三方Three.js源码、EXE或模型权重；没有声称只克隆仓库即可重现原机角色。

1. 将自己有权使用的既有角色文件另行保存在项目外。原查看器约定的主文件是`xiaolong-parts.glb`，包含`Body`、`SafetyHat`、`HatUnderside`对象，帽子的局部原点必须已经设在帽底；任意GLB不一定能正确换帽。可选检查模型名为`xiaolong-gray.glb`、`xiaolong-textured.glb`。本次不重做模型。
2. Node/npm仅在准备可选Three.js组件时需要，安装到项目外：

```powershell
$demoVendor = Join-Path $env:USERPROFILE '.codex/tools/longshi-assistant-prototype/vendor/public-runtime'
npm install --prefix $demoVendor --no-audit --no-fund three@0.186.1
$env:XIAOLONG_THREE_DIR = Join-Path $demoVendor 'node_modules/three'
$env:XIAOLONG_MODEL_DIR = 'D:/my-private-mascot-assets' # 改为你自己的项目外素材目录
python -B app.py
```

安装时联网获取官方npm包；查看器运行不依赖CDN。只配置路径，不扫描文件系统或读取其他公司资料。首次加载前检查主GLB及Three.js是否存在；有素材时使用原有真实网格、四帽和旋转逻辑，缺少配套文件时可能加载失败。当前公开整理没有再做新模型实验。

公开合成版的本机运行指针放在用户目录下`.codex/tools/longshi-assistant-prototype/runtime-public/`，与旧私有样机的指针分开。不要提交该运行目录、浏览器配置、素材目录或EXE。后续打包须另行构建，不能把此前包含真实样本的旧EXE当公开版分发。

## 公开范围和许可

见[公开核查说明](公开核查说明.md)与[素材和依赖说明](素材和依赖说明.md)。原私有实现、研究记录、历史截图和角色素材已移到原机项目外私有归档，并校验完整性；它们不会随Git克隆转移。离开原机前若需个人接续，应另行安全携带所需资料，不把它们补进公开仓库。

源码公开不自动等于MIT许可；由仓库所有者统一决定项目源码许可。本目录没有替用户授予参考图或生成角色的版权，也没有将Hunyuan自定义条款称为MIT。真实性研究和美术验收不能由这个合成演示替代。
