import requests
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
import sqlite3
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# TOKEN DAN API  ← ganti di sini
# ==========================================
TELEGRAM_TOKEN = os.getenv("8955283052:AAG01BpcuKR96ZDT5v4iDi98oNwoyFvAV50")
WEATHER_API_KEY = os.getenv("b78a67670b9d64c0647d3e445f8b4aba")
CHAT_ID_KAMU = int(os.getenv("CHAT_ID_KAMU"))

# ==========================================
# STATE untuk ConversationHandler
# ==========================================
(
    TUNGGU_TUGAS,
    TUNGGU_SELESAI,
    TUNGGU_UANG,
    TUNGGU_CUACA,
    TUNGGU_TARGET,
    TUNGGU_PENGINGAT,
    TUNGGU_KATEGORI,
    TUNGGU_NOMINAL,
    TUNGGU_KETERANGAN
) = range(9)

# ==========================================
# DATABASE
# ==========================================
conn   = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()
user_data = {}

def init_db():
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS tugas (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nama  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pengeluaran (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal     TEXT NOT NULL,
            kategori    TEXT NOT NULL,
            nominal     INTEGER NOT NULL,
            keterangan  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS histori (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            waktu TEXT NOT NULL,
            aksi  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pengaturan (
            kunci TEXT PRIMARY KEY,
            nilai TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pengingat (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            jam   TEXT NOT NULL,
            pesan TEXT NOT NULL
        );
    """)
    conn.commit()


def catat_histori(aksi: str):
    cursor.execute(
        "INSERT INTO histori (waktu, aksi) VALUES (?, ?)",
        (datetime.now().strftime("%d-%m-%Y %H:%M:%S"), aksi),
    )
    conn.commit()


def ambil_target() -> int:
    cursor.execute("SELECT nilai FROM pengaturan WHERE kunci = 'target'")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


# ==========================================
# KEYBOARD HELPERS
# ==========================================
def kb_home():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Tugas",     callback_data="menu_tugas"),
            InlineKeyboardButton("💰 Keuangan",  callback_data="menu_keuangan"),
        ],
        [
            InlineKeyboardButton("🌦️ Cuaca",     callback_data="menu_cuaca"),
            InlineKeyboardButton("📊 Statistik", callback_data="menu_statistik"),
        ],
        [
            InlineKeyboardButton("📜 Histori",   callback_data="menu_histori"),
            InlineKeyboardButton("⚙️ Pengaturan",callback_data="menu_setting"),
        ],
        [
            InlineKeyboardButton("💾 Backup",    callback_data="aksi_backup"),
        ],
    ])


def kb_tugas():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Tambah Tugas",   callback_data="aksi_tambah_tugas")],
        [InlineKeyboardButton("📋 Lihat Daftar",   callback_data="aksi_list_tugas")],
        [InlineKeyboardButton("✅ Tandai Selesai", callback_data="aksi_selesai_tugas")],
        [InlineKeyboardButton("🏠 Home",           callback_data="home")],
    ])


def kb_keuangan():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Catat Pengeluaran", callback_data="aksi_catat_uang")],
        [InlineKeyboardButton("💰 Lihat Saldo",       callback_data="aksi_saldo")],
        [
            InlineKeyboardButton("📅 Laporan Hari Ini", callback_data="aksi_laporan_hari"),
            InlineKeyboardButton("📆 Laporan Bulan",    callback_data="aksi_laporan_bulan"),
        ],
        [InlineKeyboardButton("📊 Grafik Pengeluaran", callback_data="aksi_grafik")],
        [InlineKeyboardButton("🏠 Home", callback_data="home")],
    ])


def kb_kategori():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍔 Makan",     callback_data="kat_makan"),
            InlineKeyboardButton("🚗 Transport", callback_data="kat_transport"),
        ],
        [
            InlineKeyboardButton("🛒 Belanja",   callback_data="kat_belanja"),
            InlineKeyboardButton("🎮 Hiburan",   callback_data="kat_hiburan"),
        ],
        [InlineKeyboardButton("✏️ Ketik Manual", callback_data="aksi_catat_uang_manual")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="menu_keuangan")],
        [InlineKeyboardButton("🏠 Home",    callback_data="home")],
    ])


def kb_setting():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Set Target Bulanan", callback_data="aksi_target")],
        [InlineKeyboardButton("⏰ Tambah Pengingat",   callback_data="aksi_pengingat")],
        [InlineKeyboardButton("🗑️ Hapus Semua Data",  callback_data="aksi_hapus_konfirmasi")],
        [InlineKeyboardButton("🏠 Home",               callback_data="home")],
    ])


def kb_konfirmasi_hapus():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ya, Hapus Semua", callback_data="aksi_hapus_semua"),
            InlineKeyboardButton("❌ Batal",            callback_data="menu_setting"),
        ],
    ])


def kb_back_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Home", callback_data="home")],
    ])


def kb_back(target: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Kembali", callback_data=target)],
        [InlineKeyboardButton("🏠 Home",    callback_data="home")],
    ])


# ==========================================
# TEKS SAMBUTAN
# ==========================================
TEKS_HOME = (
    "🤖 *MyAiku Bot*\n\n"
    "Asisten pribadi untuk tugas & keuangan.\n"
    "Pilih menu di bawah 👇"
)


# ==========================================
# /start
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEKS_HOME,
        reply_markup=kb_home(),
        parse_mode="Markdown",
    )


# ==========================================
# ROUTER UTAMA — semua tombol masuk sini
# ==========================================
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    # ── Navigasi Menu ──────────────────────
    if data == "home":
        await query.edit_message_text(TEKS_HOME, reply_markup=kb_home(), parse_mode="Markdown")

    elif data == "menu_tugas":
        cursor.execute("SELECT COUNT(*) FROM tugas")
        jml = cursor.fetchone()[0]
        await query.edit_message_text(
            f"📝 *MENU TUGAS*\n\nTugas aktif: *{jml}*\nPilih aksi:",
            reply_markup=kb_tugas(),
            parse_mode="Markdown",
        )

    elif data == "menu_keuangan":
        cursor.execute("SELECT SUM(nominal) FROM pengeluaran")
        total = cursor.fetchone()[0] or 0
        await query.edit_message_text(
            f"💰 *MENU KEUANGAN*\n\nTotal pengeluaran: *Rp {total:,}*\nPilih aksi:",
            reply_markup=kb_keuangan(),
            parse_mode="Markdown",
        )

    elif data == "menu_statistik":
        await _kirim_statistik_edit(query)

    elif data == "menu_histori":
        await _kirim_histori_edit(query)

    elif data == "menu_setting":
        tgt = ambil_target()
        await query.edit_message_text(
            f"⚙️ *PENGATURAN*\n\nTarget bulan ini: *Rp {tgt:,}*",
            reply_markup=kb_setting(),
            parse_mode="Markdown",
        )

    elif data == "menu_cuaca":
        await query.edit_message_text(
            "🌦️ *CEK CUACA*\n\nKetik nama kota:\nContoh: `Malang`",
            reply_markup=kb_back("home"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "cuaca"

    # ── Aksi Tugas ─────────────────────────
    elif data == "aksi_tambah_tugas":
        await query.edit_message_text(
            "📝 Ketik nama tugas baru:\nContoh: `Kerjakan PR Python`",
            reply_markup=kb_back("menu_tugas"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "tambah_tugas"

    elif data == "aksi_list_tugas":
        await _kirim_list_tugas_edit(query)

    elif data == "aksi_selesai_tugas":
        cursor.execute("SELECT id, nama FROM tugas ORDER BY id")
        rows = cursor.fetchall()
        if not rows:
            await query.edit_message_text("📝 Tidak ada tugas aktif.", reply_markup=kb_back("menu_tugas"))
            return
        pesan = "✅ *TANDAI SELESAI*\n\nKetik nomor tugas:\n\n"
        for i, (_, nama) in enumerate(rows, 1):
            pesan += f"{i}. {nama}\n"
        await query.edit_message_text(pesan, reply_markup=kb_back("menu_tugas"), parse_mode="Markdown")
        context.user_data["mode"] = "selesai_tugas"

    # ── Aksi Keuangan ──────────────────────
    elif data == "aksi_catat_uang":
        await query.edit_message_text(
            "💸 *CATAT PENGELUARAN*\n\nPilih kategori:",
            reply_markup=kb_kategori(),
            parse_mode="Markdown",
        )

    elif data == "aksi_catat_uang_manual":
        await query.edit_message_text(
            "💸 *CATAT PENGELUARAN*\n\nFormat:\n`kategori nominal keterangan`\n\nContoh:\n`makan 15000 nasi goreng`",
            reply_markup=kb_back("menu_keuangan"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "catat_uang"

    elif data in ("kat_makan", "kat_transport", "kat_belanja", "kat_hiburan"):
        kategori_map = {
            "kat_makan": "makan",
            "kat_transport": "transport",
            "kat_belanja": "belanja",
            "kat_hiburan": "hiburan",
        }
        kategori = kategori_map[data]
        context.user_data["kategori"] = kategori
        await query.edit_message_text(
            f"💸 *CATAT PENGELUARAN*\n\nKategori: *{kategori}*\n\nKetik nominal:\nContoh: `15000`",
            reply_markup=kb_back("menu_keuangan"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "catat_uang_nominal"

    elif data == "aksi_saldo":
        cursor.execute("SELECT SUM(nominal) FROM pengeluaran")
        total = cursor.fetchone()[0] or 0
        tgt   = ambil_target()
        sisa  = tgt - total
        await query.edit_message_text(
            f"💰 *SALDO*\n\n"
            f"Total Pengeluaran : *Rp {total:,}*\n"
            f"Target Bulan Ini  : *Rp {tgt:,}*\n"
            f"Sisa Budget       : *Rp {sisa:,}*",
            reply_markup=kb_back("menu_keuangan"),
            parse_mode="Markdown",
        )

    elif data == "aksi_laporan_hari":
        await _kirim_laporan_hari_edit(query)

    elif data == "aksi_laporan_bulan":
        await _kirim_laporan_bulan_edit(query)

    # ── Aksi Pengaturan ────────────────────
    elif data == "aksi_target":
        tgt = ambil_target()
        await query.edit_message_text(
            f"🎯 *SET TARGET BULANAN*\n\nTarget saat ini: *Rp {tgt:,}*\n\nKetik nominal baru:\nContoh: `2000000`",
            reply_markup=kb_back("menu_setting"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "set_target"

    elif data == "aksi_pengingat":
        await query.edit_message_text(
            "⏰ *TAMBAH PENGINGAT*\n\nFormat:\n`HH:MM pesan`\n\nContoh:\n`19:00 belajar python`",
            reply_markup=kb_back("menu_setting"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "tambah_pengingat"

    elif data == "aksi_hapus_konfirmasi":
        await query.edit_message_text(
            "⚠️ *HAPUS SEMUA DATA?*\n\nSemua tugas, pengeluaran, histori, dan pengingat akan dihapus permanen.\n\nYakin?",
            reply_markup=kb_konfirmasi_hapus(),
            parse_mode="Markdown",
        )

    elif data == "aksi_hapus_semua":
        cursor.executescript("""
            DELETE FROM tugas;
            DELETE FROM pengeluaran;
            DELETE FROM histori;
            DELETE FROM pengingat;
            DELETE FROM sqlite_sequence WHERE name IN ('tugas','pengeluaran','histori','pengingat');
        """)
        conn.commit()
        await query.edit_message_text(
            "🗑️ Semua data berhasil dihapus.",
            reply_markup=kb_back_home(),
        )

    # ── Backup ─────────────────────────────
    elif data == "aksi_backup":
        try:
            with open("database.db", "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename="database_backup.db",
                    caption="📦 Backup database berhasil dikirim!",
                )
        except FileNotFoundError:
            await query.message.reply_text("❌ File database tidak ditemukan.")

    # ── Grafik Pengeluaran ─────────────────
    elif data == "aksi_grafik":
        await _kirim_grafik(query)


# ==========================================
# HANDLER PESAN TEKS (mode-based)
# ==========================================
async def teks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode  = context.user_data.get("mode")
    teks  = update.message.text.strip()

    if not mode:
        # Tidak ada mode aktif — abaikan / tampilkan home
        await update.message.reply_text(
            "Gunakan /start untuk membuka menu.",
        )
        return

    # ── Tambah Tugas ───────────────────────
    if mode == "tambah_tugas":
        cursor.execute("INSERT INTO tugas (nama) VALUES (?)", (teks,))
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM tugas")
        total = cursor.fetchone()[0]
        catat_histori(f"Tambah tugas: {teks}")
        context.user_data.pop("mode")
        await update.message.reply_text(
            f"✅ Tugas ditambahkan!\n📝 *{teks}*\n\nTotal tugas aktif: {total}",
            parse_mode="Markdown",
            reply_markup=kb_tugas(),
        )

    # ── Selesai Tugas ──────────────────────
    elif mode == "selesai_tugas":
        try:
            nomor = int(teks)
            cursor.execute("SELECT id, nama FROM tugas ORDER BY id")
            rows  = cursor.fetchall()
            if nomor < 1 or nomor > len(rows):
                await update.message.reply_text("❌ Nomor tidak ditemukan. Coba lagi:")
                return
            row_id, nama = rows[nomor - 1]
            cursor.execute("DELETE FROM tugas WHERE id = ?", (row_id,))
            conn.commit()
            catat_histori(f"Selesai tugas: {nama}")
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"✅ Tugas selesai!\n📝 *{nama}*",
                parse_mode="Markdown",
                reply_markup=kb_tugas(),
            )
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka. Coba lagi:")

    # ── Catat Uang (manual) ────────────────
    elif mode == "catat_uang":
        bagian = teks.split()
        if len(bagian) < 3:
            await update.message.reply_text(
                "❌ Format salah.\nContoh: `makan 15000 nasi goreng`",
                parse_mode="Markdown",
            )
            return
        try:
            kategori   = bagian[0]
            nominal    = int(bagian[1])
            keterangan = " ".join(bagian[2:])
            tanggal    = datetime.now().strftime("%d-%m-%Y")
            cursor.execute(
                "INSERT INTO pengeluaran (tanggal, kategori, nominal, keterangan) VALUES (?,?,?,?)",
                (tanggal, kategori, nominal, keterangan),
            )
            conn.commit()
            catat_histori(f"{kategori} Rp{nominal:,} - {keterangan}")
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"✅ Dicatat!\n\n"
                f"🏷️ Kategori : *{kategori}*\n"
                f"💸 Nominal  : *Rp {nominal:,}*\n"
                f"📝 Ket.     : {keterangan}",
                parse_mode="Markdown",
                reply_markup=kb_keuangan(),
            )
        except ValueError:
            await update.message.reply_text("❌ Nominal harus angka. Contoh: `makan 15000 nasi goreng`", parse_mode="Markdown")

    # ── Catat Uang (via tombol) — nominal ──
    elif mode == "catat_uang_nominal":
        try:
            nominal = int(teks.replace(".", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("❌ Nominal harus angka. Coba lagi:")
            return
        context.user_data["nominal"] = nominal
        kategori = context.user_data.get("kategori", "lainnya")
        await update.message.reply_text(
            f"💸 *CATAT PENGELUARAN*\n\n"
            f"Kategori : *{kategori}*\n"
            f"Nominal  : *Rp {nominal:,}*\n\n"
            f"Ketik keterangan:\nContoh: `nasi goreng`",
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "catat_uang_keterangan"

    # ── Catat Uang (via tombol) — keterangan
    elif mode == "catat_uang_keterangan":
        keterangan = teks
        kategori   = context.user_data.get("kategori", "lainnya")
        nominal    = context.user_data.get("nominal", 0)
        tanggal    = datetime.now().strftime("%d-%m-%Y")
        cursor.execute(
            "INSERT INTO pengeluaran (tanggal, kategori, nominal, keterangan) VALUES (?,?,?,?)",
            (tanggal, kategori, nominal, keterangan),
        )
        conn.commit()
        catat_histori(f"{kategori} Rp{nominal:,} - {keterangan}")
        context.user_data.pop("mode", None)
        context.user_data.pop("kategori", None)
        context.user_data.pop("nominal", None)
        await update.message.reply_text(
            f"✅ Dicatat!\n\n"
            f"🏷️ Kategori : *{kategori}*\n"
            f"💸 Nominal  : *Rp {nominal:,}*\n"
            f"📝 Ket.     : {keterangan}",
            parse_mode="Markdown",
            reply_markup=kb_keuangan(),
        )

    # ── Cek Cuaca ──────────────────────────
    elif mode == "cuaca":
        kota = teks
        try:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={kota}&appid={WEATHER_API_KEY}&units=metric&lang=id"
            )
            resp = requests.get(url, timeout=10)
            d    = resp.json()
            if d.get("cod") != 200:
                await update.message.reply_text("❌ Kota tidak ditemukan. Coba ketik ulang:")
                return
            suhu      = d["main"]["temp"]
            kelembapan= d["main"]["humidity"]
            kondisi   = d["weather"][0]["description"]
            angin     = d["wind"]["speed"]
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"🌦️ *Cuaca di {kota.title()}*\n\n"
                f"🌡️ Suhu       : *{suhu}°C*\n"
                f"💧 Kelembapan : *{kelembapan}%*\n"
                f"🌬️ Angin      : *{angin} m/s*\n"
                f"☁️ Kondisi    : {kondisi}",
                parse_mode="Markdown",
                reply_markup=kb_back_home(),
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # ── Set Target ─────────────────────────
    elif mode == "set_target":
        try:
            nominal = int(teks.replace(".", "").replace(",", ""))
            cursor.execute(
                "INSERT OR REPLACE INTO pengaturan (kunci, nilai) VALUES ('target', ?)",
                (str(nominal),),
            )
            conn.commit()
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"🎯 Target bulan ini disimpan:\n*Rp {nominal:,}*",
                parse_mode="Markdown",
                reply_markup=kb_setting(),
            )
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka saja. Contoh: `2000000`", parse_mode="Markdown")

    # ── Tambah Pengingat ───────────────────
    elif mode == "tambah_pengingat":
        bagian = teks.split(maxsplit=1)
        if len(bagian) < 2:
            await update.message.reply_text(
                "❌ Format salah.\nContoh: `19:00 belajar python`",
                parse_mode="Markdown",
            )
            return
        jam, pesan_ingat = bagian[0], bagian[1]
        try:
            datetime.strptime(jam, "%H:%M")
        except ValueError:
            await update.message.reply_text("❌ Format jam salah. Gunakan HH:MM.\nContoh: `19:00`", parse_mode="Markdown")
            return
        cursor.execute("INSERT INTO pengingat (jam, pesan) VALUES (?, ?)", (jam, pesan_ingat))
        conn.commit()
        context.user_data.pop("mode")
        await update.message.reply_text(
            f"⏰ Pengingat disimpan!\n\n🕐 Jam   : *{jam}*\n📢 Pesan : {pesan_ingat}",
            parse_mode="Markdown",
            reply_markup=kb_setting(),
        )


# ==========================================
# FUNGSI BANTU — render konten
# ==========================================
async def _kirim_list_tugas_edit(query):
    cursor.execute("SELECT id, nama FROM tugas ORDER BY id")
    rows = cursor.fetchall()
    if not rows:
        await query.edit_message_text(
            "📝 Tidak ada tugas aktif.",
            reply_markup=kb_back("menu_tugas"),
        )
        return
    pesan = "📝 *DAFTAR TUGAS*\n\n"
    for i, (_, nama) in enumerate(rows, 1):
        pesan += f"{i}. {nama}\n"
    await query.edit_message_text(pesan, reply_markup=kb_back("menu_tugas"), parse_mode="Markdown")


async def _kirim_statistik_edit(query):
    cursor.execute("SELECT SUM(nominal), COUNT(*) FROM pengeluaran")
    row    = cursor.fetchone()
    total  = row[0] or 0
    jumlah = row[1] or 0

    if jumlah == 0:
        await query.edit_message_text(
            "📊 Belum ada data pengeluaran.",
            reply_markup=kb_back_home(),
        )
        return

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml
        FROM pengeluaran GROUP BY kategori ORDER BY jml DESC LIMIT 5
    """)
    kat_rows = cursor.fetchall()

    rata      = total / max(1, datetime.now().day)
    tgt       = ambil_target()
    sisa      = tgt - total
    persen    = round((total / tgt * 100), 1) if tgt > 0 else 0

    # Progress bar visual
    bar_isi   = min(10, int(persen / 10))
    bar       = "█" * bar_isi + "░" * (10 - bar_isi)

    pesan  = f"📈 *STATISTIK KEUANGAN*\n\n"
    pesan += f"💸 Total Pengeluaran : *Rp {total:,}*\n"
    pesan += f"🧾 Jumlah Transaksi  : *{jumlah}*\n"
    pesan += f"📊 Rata-rata/hari    : *Rp {int(rata):,}*\n\n"
    pesan += f"🎯 Target Bulan      : *Rp {tgt:,}*\n"
    pesan += f"💰 Sisa Budget       : *Rp {sisa:,}*\n"
    pesan += f"📉 Terpakai          : `{bar}` {persen}%\n\n"
    pesan += f"🏆 *Top Kategori:*\n"
    for k, v in kat_rows:
        pesan += f"   • {k}: Rp {v:,}\n"

    await query.edit_message_text(pesan, reply_markup=kb_back_home(), parse_mode="Markdown")


async def _kirim_histori_edit(query):
    cursor.execute("SELECT waktu, aksi FROM histori ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    if not rows:
        await query.edit_message_text("📜 Belum ada histori.", reply_markup=kb_back_home())
        return
    pesan = "📜 *HISTORI TERAKHIR*\n\n"
    for waktu, aksi in reversed(rows):
        pesan += f"🕐 {waktu}\n➡️ {aksi}\n\n"
    await query.edit_message_text(pesan, reply_markup=kb_back_home(), parse_mode="Markdown")


async def _kirim_laporan_hari_edit(query):
    hari_ini = datetime.now().strftime("%d-%m-%Y")
    cursor.execute(
        "SELECT nominal, keterangan, kategori FROM pengeluaran WHERE tanggal = ?",
        (hari_ini,),
    )
    rows = cursor.fetchall()
    if not rows:
        await query.edit_message_text(
            f"📅 Belum ada pengeluaran hari ini ({hari_ini}).",
            reply_markup=kb_back("menu_keuangan"),
        )
        return
    total = 0
    pesan = f"📅 *LAPORAN {hari_ini}*\n\n"
    for nominal, keterangan, kategori in rows:
        pesan += f"🏷️ {kategori} — Rp {nominal:,}\n📝 {keterangan}\n\n"
        total += nominal
    pesan += f"━━━━━━━━━━━━━━\n💰 *TOTAL: Rp {total:,}*"
    await query.edit_message_text(pesan, reply_markup=kb_back("menu_keuangan"), parse_mode="Markdown")


async def _kirim_laporan_bulan_edit(query):
    bulan = datetime.now().strftime("%m-%Y")
    cursor.execute(
        "SELECT SUM(nominal), COUNT(*) FROM pengeluaran WHERE substr(tanggal, 4, 7) = ?",
        (bulan,),
    )
    total, jumlah = cursor.fetchone()
    total  = total  or 0
    jumlah = jumlah or 0

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml
        FROM pengeluaran
        WHERE substr(tanggal, 4, 7) = ?
        GROUP BY kategori ORDER BY jml DESC
    """, (bulan,))
    kat_rows = cursor.fetchall()

    pesan  = f"📆 *LAPORAN BULAN {bulan}*\n\n"
    pesan += f"🧾 Jumlah Transaksi : *{jumlah}*\n"
    pesan += f"💸 Total Pengeluaran: *Rp {total:,}*\n\n"
    if kat_rows:
        pesan += "📂 *Per Kategori:*\n"
        for k, v in kat_rows:
            pesan += f"   • {k}: Rp {v:,}\n"

    await query.edit_message_text(pesan, reply_markup=kb_back("menu_keuangan"), parse_mode="Markdown")


async def _kirim_grafik(query):
    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml
        FROM pengeluaran
        GROUP BY kategori ORDER BY jml DESC
    """)
    rows = cursor.fetchall()

    if not rows:
        await query.edit_message_text(
            "📊 Belum ada data pengeluaran untuk dibuat grafik.",
            reply_markup=kb_back("menu_keuangan"),
        )
        return

    kategori = [r[0] for r in rows]
    nominal  = [r[1] for r in rows]

    plt.figure(figsize=(8, 5))
    plt.bar(kategori, nominal, color="#4C9AFF")
    plt.title("Pengeluaran per Kategori")
    plt.ylabel("Rupiah")
    plt.tight_layout()

    path = "grafik.png"
    plt.savefig(path)
    plt.close()

    with open(path, "rb") as foto:
        await query.message.reply_photo(
            photo=foto,
            caption="📊 *Grafik Pengeluaran per Kategori*",
            parse_mode="Markdown",
            reply_markup=kb_back("menu_keuangan"),
        )

    os.remove(path)


# ==========================================
# JOB — CEK PENGINGAT setiap menit
# ==========================================
async def cek_pengingat(context: ContextTypes.DEFAULT_TYPE):
    sekarang = datetime.now().strftime("%H:%M")
    cursor.execute("SELECT id, pesan FROM pengingat WHERE jam = ?", (sekarang,))
    rows = cursor.fetchall()
    for row_id, pesan in rows:
        await context.bot.send_message(
            chat_id=CHAT_ID_KAMU,
            text=f"⏰ *Pengingat!*\n\n{pesan}",
            parse_mode="Markdown",
        )
        cursor.execute("DELETE FROM pengingat WHERE id = ?", (row_id,))
    if rows:
        conn.commit()


# ==========================================
# COMMAND SHORTCUTS (tetap bisa pakai slash)
# ==========================================
async def cmd_tugas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Contoh: `/tugas Kerjakan PR Python`", parse_mode="Markdown")
        return
    nama = " ".join(context.args)
    cursor.execute("INSERT INTO tugas (nama) VALUES (?)", (nama,))
    conn.commit()
    catat_histori(f"Tambah tugas: {nama}")
    cursor.execute("SELECT COUNT(*) FROM tugas")
    total = cursor.fetchone()[0]
    await update.message.reply_text(
        f"✅ Tugas ditambahkan!\n📝 *{nama}*\nTotal aktif: {total}",
        parse_mode="Markdown",
        reply_markup=kb_tugas(),
    )


async def cmd_uang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Contoh: `/uang makan 15000 nasi goreng`", parse_mode="Markdown")
        return
    try:
        kategori   = context.args[0]
        nominal    = int(context.args[1])
        keterangan = " ".join(context.args[2:])
        tanggal    = datetime.now().strftime("%d-%m-%Y")
        cursor.execute(
            "INSERT INTO pengeluaran (tanggal, kategori, nominal, keterangan) VALUES (?,?,?,?)",
            (tanggal, kategori, nominal, keterangan),
        )
        conn.commit()
        catat_histori(f"{kategori} Rp{nominal:,} - {keterangan}")
        await update.message.reply_text(
            f"✅ Dicatat!\n🏷️ {kategori} — *Rp {nominal:,}*",
            parse_mode="Markdown",
            reply_markup=kb_keuangan(),
        )
    except ValueError:
        await update.message.reply_text("❌ Nominal harus angka.")


async def cmd_cuaca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Contoh: `/cuaca Malang`", parse_mode="Markdown")
        return
    kota = " ".join(context.args)
    try:
        url  = f"https://api.openweathermap.org/data/2.5/weather?q={kota}&appid={WEATHER_API_KEY}&units=metric&lang=id"
        resp = requests.get(url, timeout=10)
        d    = resp.json()
        if d.get("cod") != 200:
            await update.message.reply_text("❌ Kota tidak ditemukan.")
            return
        await update.message.reply_text(
            f"🌦️ *Cuaca di {kota.title()}*\n\n"
            f"🌡️ Suhu: *{d['main']['temp']}°C*\n"
            f"💧 Kelembapan: *{d['main']['humidity']}%*\n"
            f"☁️ Kondisi: {d['weather'][0]['description']}",
            parse_mode="Markdown",
            reply_markup=kb_back_home(),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    init_db()
    print("✅ Database SQLite siap.")
    print("🤖 Bot V2 menyala...")
    
    print("TOKEN:", repr(TELEGRAM_TOKEN))
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("tugas",   cmd_tugas))
    app.add_handler(CommandHandler("uang",    cmd_uang))
    app.add_handler(CommandHandler("cuaca",   cmd_cuaca))

    # Inline keyboard router
    app.add_handler(CallbackQueryHandler(router))

    # Semua pesan teks biasa → mode handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, teks_handler))

    # Job pengingat
    app.job_queue.run_repeating(cek_pengingat, interval=60, first=10)

    app.run_polling()