# Fuji Sakura Vista — Arakurayama First Light

**[▶ 互動 3D Demo (GitHub Pages)](https://malilion.github.io/fuji-sakura-vista/)** · Blender 4.5 原始檔 · Cycles 渲染 · Three.js 即時場景

新倉山淺間公園春日清晨的程序生成 Blender 場景，以及由同一份 `.blend` 匯出的網頁互動版本。五層忠靈塔、下行石階、朱紅欄杆、暖色燈籠、六種櫻花樹型、富士吉田市街與富士山，全部由一支腳本以固定亂數種子建立，不依賴任何外部貼圖或掃描資產。步道與燈籠配置為藝術化重組，並非實地測繪還原。

[![First Light — Cycles 靜幀](renders/still/frame_0288.png)](https://malilion.github.io/fuji-sakura-vista/)

| | Cycles 離線渲染 | Three.js 即時場景 |
|---|---|---|
| 來源 | `arakurayama_sunrise.blend` (GitHub Release) | `web/assets/arakurayama.glb` (Draco, 7.9 MB) |
| 幾何 | 3,759 物件 · 36.6M 多邊形（櫻花為實例） | 28 網格 · 112 draw calls · 13.0M 三角形 / 幀 |
| 櫻花 | 6 種樹型共用網格 × 196 棵 · Geometry Nodes 微風 | `InstancedMesh` · 頂點著色器微風 · 近 / 遠 LOD |
| 光影 | 清晨方向光 · 天空貼圖 · 8 盞燈籠點光 · 山谷薄霧 | 方向光 + 半球光 · 漸層天空著色器 · 8 盞點光 · 指數霧 |
| 色彩 | AgX | AgX（`THREE.AgXToneMapping`） |
| 產出 | 1920×1080 · 96 spp 靜幀 · 12 秒動態預覽 | 12 秒鏡頭推進重播 · 軌道攝影機 · 飄落花瓣 |

## 專案結構

```
arakurayama_sunrise.blend   主要成果（放在 GitHub Releases，不在 git 內）
scripts/
  build_scene.py            以 bpy 從零建立整個場景（固定種子 829）
  render_scene.py           preview / still / animation / animatic 渲染預設
  validate_scene.py         重載 .blend 的自動檢查
  encode_preview.py         動態預覽 MP4 編碼與 ffprobe 驗證
  export_web.py             產生網頁用 glTF 與 export_manifest.json
web/                        GitHub Pages 站台（純靜態，無建置步驟）
  index.html · css/ · js/scene.js · js/main.js
  assets/arakurayama.glb · still.jpg · preview.mp4
renders/                    實際渲染成果與各批次 render_log.json
scene_manifest.json · validation.json · QA.md
```

## 互動網站

網站以 [Three.js r170](https://threejs.org) 直接載入 glTF，無打包工具；`web/` 目錄即為部署內容。

- **載入**：`GLTFLoader` + `DRACOLoader`，7.9 MB 檔案在 Draco 解碼後約 13.0M 三角形。
- **櫻花**：glTF 內 392 個櫻花節點共用 18 份網格（6 種樹型 × 枝幹 / 近景花 / 遠景花），`scene.js` 依幾何合併為 `InstancedMesh`（49 棵 / 批），微風在 `onBeforeCompile` 注入頂點著色器，位移隨樹高平方增強、每棵樹相位不同。
- **光線**：太陽方向來自 `.blend` 的 `Low morning sun` 旋轉、燈籠位置與功率來自 8 盞 `Amber lantern practical`；`Washi glow` 材質保留 `KHR_materials_emissive_strength`。
- **攝影機**：30 mm 鏡頭依長邊換算 FOV；「重播 12 秒推進」使用第 1 與第 288 格相同的位置與傾角，結束後交給 `OrbitControls`。
- **富士山積雪**：Cycles 以 `snow_coverage` 點屬性混合岩石與雪色；匯出時烘焙為 `COLOR_0` 頂點色。
- **控制項**：微風、飄落花瓣、自動環繞、陰影開關、回到主構圖、全螢幕；中 / 英介面切換。
- **後備**：無 WebGL 時顯示 Cycles 靜幀。

本機預覽：

```sh
python3 -m http.server 8765 --directory web
```

## 匯出網頁版場景

`scripts/export_web.py` 讀取 `.blend` 但不回存，全部在記憶體內處理：

1. 移除飄落花瓣、燈光、太陽、天空與攝影機集合（網站以 Three.js 重建）。
2. 櫻花以「整朵花」為單位抽樣（每朵 41 面）：近景樹保留 34%、`y > 112 m` 的遠景樹保留 11%，6 種樹型共 12 份 LOD 網格；常綠針葉減半。
3. 程序材質攤平：切斷 Base Color 與 Normal 的節點連線，改用建場時記錄的 `diffuse_color`；花瓣的半透明混合改為直接輸出 Principled。
4. 富士山 `snow_coverage` 烘焙為頂點色。
5. 套用修改器，依集合合併靜態物件（石階、欄杆、五層塔、燈籠、常綠樹、地面、市街、富士山）。
6. 以 Draco 壓縮輸出 GLB，並寫入 `web/assets/export_manifest.json`。

```sh
.venv/bin/python scripts/export_web.py
# 可調整密度
.venv/bin/python scripts/export_web.py --near-keep .5 --far-keep .15
```

## Headless 環境

使用 Python 3.11 與 Blender 4.5.3 的官方 `bpy` Python 模組；建場、渲染與匯出均不啟動桌面視窗。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # 或 requirements-lock.txt 重現已驗證版本
```

```sh
# 重建完整場景並產生低解析度預覽
.venv/bin/python scripts/build_scene.py --render preview

# 只重建 .blend
.venv/bin/python scripts/build_scene.py --render none

# 檢查開頭、中間與結尾構圖
.venv/bin/python scripts/render_scene.py --preset preview --frames 1,144,288

# 2560 px / 192 samples 主視覺
.venv/bin/python scripts/render_scene.py --preset still --frames 288

# 1920 × 1080 動畫 PNG 序列；可分段執行或重算缺格
.venv/bin/python scripts/render_scene.py --preset animation --start 1 --end 288

# 多層 scene-linear EXR
.venv/bin/python scripts/render_scene.py --preset still --frames 288 --exr

# 低解析度動態預覽
.venv/bin/python scripts/render_scene.py --preset animatic --start 1 --end 288 --step 3 --samples 8
python3 scripts/encode_preview.py

# 驗證五層塔、攝影機框內位置、花瓣位移、外部貼圖依賴
.venv/bin/python scripts/validate_scene.py
```

也可使用已安裝的 Blender：

```sh
blender --background --python scripts/build_scene.py -- --render preview
blender --background --python scripts/export_web.py
```

macOS 會偵測 Metal；不支援時使用 CPU，可在渲染指令加入 `--device CPU`。

完整動畫序列完成後可編碼：

```sh
ffmpeg -framerate 24 -start_number 1 -i renders/frames/frame_%04d.png -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart renders/first_light.mp4
```

## 場景內容

- 五層忠靈塔：逐層收分、曲面出簷、四角戧脊與脊端、斗栱層疊、格子窗、朱紅構架、欄杆、屋面接縫、銅綠斑塊、相輪。
- 下降石階（中央踏面磨光、邊緣沉降與崩角、縫隙青苔）、不規則砌石邊牆（含地衣石）、朱紅欄杆、暖色燈籠與落花。
- 六種櫻花樹型（染井吉野、山櫻、老樹、垂枝、幼樹）共用網格，花朵以短枝上的繖形花序成簇；Geometry Nodes 微風、常綠樹與草叢。
- 富士吉田市街、山麓、富士山：多頻段噪聲相位的 V 形侵蝕溝向下加深，雪線沿溝底成舌狀延伸、迎風面受風蝕。
- Cycles、AgX、清晨方向光、局部山谷薄霧。
- 24 fps、288 格（12 秒）攝影機推進與 90 片獨立花瓣動畫。

## 取得 .blend

`.blend` 不放在 git 內，而是作為 [GitHub Release v1.1](https://github.com/malilion/fuji-sakura-vista/releases/tag/v1.1) 附件提供——不計流量配額，clone 也不需要 git-lfs：

```sh
curl -L -o arakurayama_sunrise.blend https://github.com/malilion/fuji-sakura-vista/releases/latest/download/arakurayama_sunrise.blend
shasum -a 256 arakurayama_sunrise.blend
# d6fca7d21da4e7f36d8401e93daa43fa60ece277ba007b0f92271357db12d109
```

或直接從腳本重建，結果相同（固定種子 829）：

```sh
.venv/bin/python scripts/build_scene.py --render none
```

## 部署

`.github/workflows/pages.yml` 在 `web/` 有變動時把該目錄上傳為 GitHub Pages artifact 並部署；不需要 Node 或任何建置步驟。Pages 來源需設定為 **GitHub Actions**。

## 定位與後續

v1.1 完成了 `QA.md` 初版列出的四項精修：忠靈塔逐層收分、戧脊、斗栱與格子窗；六種櫻花樹型與成簇花序；富士山噪聲侵蝕溝與迎風雪線；石階與砌牆的非均勻老化。仍未做的是正式 24 fps 高取樣序列——單格 1080p / 96 spp 在 Metal 上約 4.5 分鐘，288 格約需 22 小時，指令已列於上方 `animation` 預設。目前不宣稱為攝影測量或寫實掃描資產。
