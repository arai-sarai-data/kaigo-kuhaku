# 介護の空白地帯

親が住む町に、訪問介護はあるか。75歳以上の人口あたりの介護事業所の数を、全国の市区町村で比べました。

公開ページ：https://arai-sarai-data.github.io/kaigo-kuhaku/

## 仕組み

- `fetch.py` が公式の公開データを取得・検証・集計し、`docs/data/` に JSON を書き出します。
- GitHub Actions（`.github/workflows/update.yml`）が毎月2日に自動で実行し、GitHub Pages に公開します。
- 元データの形式が想定と違うときは **数字を推測で埋めずに停止** します（前回の正しいデータが表示され続けます）。停止した理由は Actions のログに `データ検証で停止しました` として出ます。

## 最初の設定（1回だけ）

1. このフォルダの中身を `arai-sarai-data/kaigo-kuhaku` リポジトリ（Public）に置く。
2. Settings → Pages → Build and deployment の Source を **GitHub Actions** にする。
3. Settings → Actions → General → Workflow permissions を **Read and write permissions** にする。
4. Actions タブ → `update` → **Run workflow** で初回のデータ取得を実行する。

## 出典

- 厚生労働省の介護サービス情報公表システムに登録された事業所の一覧と、総務省の年齢別人口を組み合わせ、介護サービスが足りていない可能性がある地域を示します

各データの利用条件に従い、出典を明記して加工・公開しています（`docs/about.html`）。
