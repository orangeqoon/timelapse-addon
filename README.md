# TIMELAPSE Addon for Blender 5.2+

Blender公式の `Timelapse_extension` の課題を解消し、プロフェッショナルな制作フロー（特にグリースペンシル作画・スカルプト等の作業快適性）に対応した高機能タイムラプス拡張機能です。

---

## 🌟 主な特徴

1. **作画ラグ・ペン引っかかりの完全解消（スマートディレイ & 高速保存）**
   - **スマートディレイ（デフォルトON）**: ペン先がタブレットに触れている間・マウスドラッグ中は撮影を自動保留し、ペンを画面から離した瞬間にキャプチャ。作画中の引っかかりを100%防止。
   - **JPG高速書き出し（デフォルト）**: 1枚あたり約15ms（PNGの1/5以下）で保存。
   - **PNG非同期書き出し**: ロスレスPNG選択時は、メインスレッドでエンコード完了したバイト列を純Pythonバックグラウンドスレッドでディスクへ書き込み、ディスクI/Oによるブロッキングを排除。
2. **撮影トリガー方式の選択**
   - **時間間隔モード（デフォルト）**: 指定秒数（例: 5秒）ごとに自動撮影。離席時はアイドル検知で自動一時停止。
   - **アクション / ストローク連動モード**: グリースペンシル作画等で、ペンを離した回数（Nストロークごと）で1枚撮影。描いていない時間は自然に撮影が止まり、無駄撮りを防ぎます。
3. **3Dビューポート限定キャプチャ（UI排除）**
   - ウィンドウ全体のスクショではなく、3Dビューポート領域（作業画面）のみを切り出して記録。
   - **WYSIWYG モード (デフォルト)**: Blender 5.2公式の `imbuf` API を採用し、作業中のアングル・シェーディングを高速かつ正確に記録。
   - **Clean OpenGL モード**: ギズモやUIオーバーレイを排除したクリーンなレンダリングを出力。
4. **ヘッダー常駐 & ⚙ ポップオーバーUI**
   - 3Dビューポートのヘッダーにコンパクトに常駐：`[ ▶ Timelapse ][ ⚙ ]`
   - `⚙` ボタンをクリックすると、その場で吹き出し（Popover）が開き、トリガー方式、ファイル形式、スマートディレイ、保存先、MP4設定をワンクリックで変更可能。
   - 録画中は `[ REC 00:15 (23) ][ ⚙ ]` と経過時間・コマ数がリアルタイム表示。
5. **完全非ブロッキング MP4 動画出力 ＆ 動画生成後の画像自動削除（デフォルトON）**
   - 撮影停止時、Blender自身のバックグラウンドプロセス（`blender -b --factory-startup -P render_worker.py`）を呼び出し、**BlenderのUIを一切固めずに裏でMP4を一発生成**。
   - **自動ディスククリーンアップ（デフォルトON）**: MP4が正常に出力されたら、役目を終えた大量の静止画（JPEG/PNG）を自動的に削除し、ストレージの圧迫を防止。「Delete Images after MP4」のチェックを外せば生データを残すことも可能。
   - **HandBrake相当の高圧縮 / H.265 (HEVC) 対応**: 画質を落とさずにファイルサイズを大幅削減する圧縮プリセットを完備。
6. **設定の完全永続化**
   - 出力先ディレクトリやベースファイル名を `Scene` に保持。Blendファイルを保存・開き直してもリセットされません。

---

## 📁 ディレクトリ構成

```text
blender_timelapse_mod/
├── blender_manifest.toml   # Blender Extensions規格マニフェスト (id: smart_timelapse)
├── __init__.py             # ライフサイクル管理、タイマー制御、開始/停止/トグル、ディスクワーカー管理
├── capture.py              # キャプチャエンジン (imbuf保存, 純Pythonディスクワーカー, 連番管理)
├── render_worker.py        # 独立プロセスMP4レンダーワーカー（C++クラッシュ完全排除）
├── video_export.py         # レンダーワーカー呼び出しインターフェース
├── activity_tracker.py     # ストローク接触検知(スマートディレイ) + アクションカウンタ + アイドル検知
├── prefs.py                # AddonPreferences (初期設定・動画品質)
├── ui.py                   # ヘッダー常駐ボタン、⚙ポップオーバーUI、Nパネル
└── README.md               # 本ドキュメント
```

---

## 🚀 インストール手順

### 方法 1: Blender 5.2 の拡張機能フォルダへ直接配置（推奨）
1. `c:\scripts\blender_timelapse_mod\` フォルダを以下のディレクトリへコピー：
   `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\smart_timelapse\`
2. Blender 5.2 を起動（または「設定 > 拡張機能」でリフレッシュ）し、「Smart Timelapse」を有効化。

---

## ⌨️ ショートカットキー
- **`Ctrl + Shift + T`** (3D View): タイムラプス録画の開始 / 停止 トグル

---

## 📜 Credits & License
- **Author**: orangeqoon
- **License**: GNU General Public License v3.0 or later (GPL-3.0-or-later)
- **Original Work**: Based on `Timelapse_extension` by Blender Foundation & Antonio Vazquez.
