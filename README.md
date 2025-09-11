# sympa_ctl.py

Sympa のメーリングリストを **CSV ドリブンで作成・更新・削除**したり、**メンバー一覧をCSVでエクスポート**するための小さなCLIセットです。

* `sympa_ctl` … CSVを読み、`CREATE` / `REPLACE` / `REMOVE` を実行
* `sympa_export` … MLのメンバー（memberロール）を `"ml名","ユーザ名"` 形式で出力

---

## インストール

> ここでは **`sympa_ctl` と `sympa_export`** をどこからでも実行できるように設定します。

1. アーカイブを展開

```bash
tar xzf sympa_ctl.tgz
```

2. 実行ディレクトリを配置（例：`/usr/local/bin/` 配下）

```bash
sudo mv sympa_ctl /usr/local/bin/
```

3. パスを通す（`~/.bashrc` か `~/.bash_profile` に追記）

```bash
# /usr/local/bin/sympa_ctl を PATH に追加
export PATH="/usr/local/bin/sympa_ctl:$PATH"
```

4. コマンド名のエイリアスを作成（同じく `~/.bashrc` か `~/.bash_profile` に追記）

```bash
# 実行ファイルに実行権限が無い場合は付与
chmod +x /usr/local/bin/sympa_ctl/sympa_ctl_main.py
chmod +x /usr/local/bin/sympa_ctl/export_members.py

# 使いやすい別名を用意
alias sympa_ctl="/usr/bin/env python3 /usr/local/bin/sympa_ctl/sympa_ctl_main.py"
alias sympa_export="/usr/bin/env python3 /usr/local/bin/sympa_ctl/export_members.py"
```

5. シェルを再読み込み

```bash
source ~/.bashrc    # もしくは source ~/.bash_profile
```

> ※ 必要に応じて `config.py`（`SYMPA_CMD` / `DOMAIN` / `LISTFILE_DIR` などの設定）を `/usr/local/bin/sympa_ctl/` 直下に配置してください。
> ※ Python 3 が必要です。

---

## 使い方

### 1) メンバーCSV出力：`sympa_export`

* 役割：メーリングリストの **member** ロールを CSV で出力します
* 形式：ヘッダ無し、各行が `"ml名","ユーザ名（メールアドレス）"`

#### 使い方

```bash
# すべてのMLのメンバーを出力
sympa_export
# または
sympa_export '*'

# 特定MLのメンバーを出力
sympa_export mylist
```

#### 出力例

```
"dev-team","alice@example.com"
"dev-team","bob@example.com"
"ops","mladmin@example.com"
```

---

### 2) ML操作：`sympa_ctl`

* 役割：CSVの指示に従い、SympaのMLを **CREATE / REPLACE / REMOVE** します
* 成功/失敗は最小限のログを標準出力/標準エラーに出します
* `CREATE` では `.list` を読み込んで XML を生成 → 作成 → メンバー/エディタ投入
  途中で失敗した場合は `purge` でロールバックします
* `REPLACE` は **既存のロールを全削除**し `.list` に基づきオーナー/メンバー/エディタを再投入
* `REMOVE` はリストを消去（`purge`）します

#### 使い方

```bash
sympa_ctl <csv_file>
```

#### CSVファイルの書式（インライン例）

* カンマ区切り / ヘッダ無し / 1行＝1オペレーション
* 列：`CMD,LISTNAME,DESCRIPTION`
* `CMD` は `CREATE` / `REPLACE` / `REMOVE` のいずれか

```
CREATE,dev-team,Developers primary list
REPLACE,ops,Operations list
REMOVE,old-announce,Deprecated announce list
```

> `CREATE` と `REPLACE` 実行時は、`LISTFILE_DIR` 配下に `<LISTNAME>.list` が必要です。

---

## .list ファイルの書式

各ロール（owner / editor / member）のメールアドレスをセクションごとに列挙します。

```
[owner]
mladmin@example.com

[editor]
tanaka@example.com
yamada@example.com

[member]
suzuki@example.com
yokoyama@example.com
```

* `#` または `;` 以降はコメント
* セクションは `[owner]`, `[editor]`, `[member]` の3種
* 空行OK

---

## 動作のポイント（抜粋）

* `sympa_ctl` の **CREATE**：
  `.list` → XML生成 → `create` 実行 → メンバー/エディタ投入
  途中失敗時は `purge` を実行（バックアップ/リストアはしません）
* **REPLACE**：
  既存のメンバー/エディタ/オーナーを削除 → `.list` の内容を再投入
  途中失敗時はバックアップから `restore`
* **REMOVE**：
  既存チェック後、バックアップを取り `purge` 実行（失敗時は `restore`）

---

## よくあるエラー

* `Failed to load config`
  → `/usr/local/bin/sympa_ctl/config.py` が見つからない/不正。`SYMPA_CMD`, `DOMAIN`, `LISTFILE_DIR` を定義してください。
* `list not found`（`sympa_export`）
  → 指定したMLが存在しないか、Sympa側の権限/設定により参照できません。
* `.list not found`（`sympa_ctl`）
  → `LISTFILE_DIR` 配下に `<LISTNAME>.list` を置いてください。

---

## 例：最小のセットアップ

```bash
tar xzf sympa_ctl.tgz
sudo mv sympa_ctl /usr/local/bin/

cat >/usr/local/bin/sympa_ctl/config.py <<'PY'
SYMPA_CMD = "/usr/sbin/sympa"
DOMAIN = "sympa.example.com"
LISTFILE_DIR = "/usr/local/bin/sympa_ctl/lists"
PY

mkdir -p /usr/local/bin/sympa_ctl/lists
cat >/usr/local/bin/sympa_ctl/lists/dev-team.list <<'LIST'
[owner]
mladmin@example.com
[member]
tanaka@example.com
yamada@example.com
LIST

echo 'export PATH="/usr/local/bin/sympa_ctl:$PATH"' >>~/.bashrc
echo 'alias sympa_ctl="/usr/bin/env python3 /usr/local/bin/sympa_ctl/sympa_ctl_main.py"' >>~/.bashrc
echo 'alias sympa_export="/usr/bin/env python3 /usr/local/bin/sympa_ctl/export_members.py"' >>~/.bashrc
source ~/.bashrc

cat > /tmp/op.csv <<'CSV'
CREATE,dev-team,Developers primary list
CSV

sympa_ctl /tmp/op.csv
sympa_export dev-team
```

以上です。必要に応じてパスや設定値は環境に合わせて調整してください。

