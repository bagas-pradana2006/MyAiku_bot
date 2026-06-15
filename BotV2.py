import io
import os
import requests
import pytz
from datetime import datetime, time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
# TOKEN DAN API
# ==========================================
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
CHAT_ID_KAMU    = int(os.getenv("CHAT_ID_KAMU"))

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
        CREATE TABLE IF NOT EXISTS target_tabungan (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            target  INTEGER NOT NULL,
            bulan   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jurnal (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL,
            isi     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deadline_tugas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL,
            matkul  TEXT NOT NULL,
            tugas   TEXT NOT NULL,
            selesai INTEGER DEFAULT 0
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
    """Satu sumber target: tabel target_tabungan bulan ini."""
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT target FROM target_tabungan
        WHERE bulan = ?
        ORDER BY id DESC LIMIT 1
    """, (bulan,))
    row = cursor.fetchone()
    return int(row[0]) if row else 0


# ==========================================
# KEYBOARD HELPERS
# ==========================================
def kb_home():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Keuangan", callback_data="menu_keuangan"),
            InlineKeyboardButton("📚 Produktivitas", callback_data="menu_produktivitas"),
        ],
        [
            InlineKeyboardButton("🌦️ Cuaca", callback_data="menu_cuaca"),
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="menu_setting"),
        ],
        [
            InlineKeyboardButton("💾 Backup", callback_data="aksi_backup"),
        ],
    ])


def kb_produktivitas():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📔 Jurnal Hari Ini",     callback_data="aksi_jurnal")],
        [InlineKeyboardButton("✏️ Tambah Jurnal",       callback_data="aksi_tambah_jurnal")],
        [InlineKeyboardButton("📅 Tambah Deadline",     callback_data="aksi_deadline")],
        [InlineKeyboardButton("📋 List Deadline",       callback_data="aksi_listdeadline")],
        [InlineKeyboardButton("✅ Selesaikan Deadline", callback_data="aksi_selesaideadline")],
        [InlineKeyboardButton("🏠 Home",                callback_data="home")],
    ])


def kb_keuangan():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Catat Pengeluaran",   callback_data="aksi_catat_uang")],
        [InlineKeyboardButton("💰 Lihat Saldo",         callback_data="aksi_saldo")],
        [
            InlineKeyboardButton("🎯 Target Bulanan",   callback_data="aksi_target"),
            InlineKeyboardButton("📈 Progress Target",  callback_data="aksi_progres"),
        ],
        [
            InlineKeyboardButton("📅 Laporan Hari Ini", callback_data="aksi_laporan_hari"),
            InlineKeyboardButton("📆 Laporan Bulan",    callback_data="aksi_laporan_bulan"),
        ],
        [InlineKeyboardButton("📊 Rekap Bulanan",       callback_data="aksi_rekap_bulan")],
        [InlineKeyboardButton("📉 Statistik",           callback_data="menu_statistik")],
        [InlineKeyboardButton("📊 Grafik Pengeluaran",  callback_data="aksi_grafik")],
        [InlineKeyboardButton("🏠 Home",                callback_data="home")],
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
        [InlineKeyboardButton("⬅️ Kembali",      callback_data="menu_keuangan")],
        [InlineKeyboardButton("🏠 Home",         callback_data="home")],
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

    elif data == "menu_produktivitas":
        cursor.execute("SELECT COUNT(*) FROM deadline_tugas WHERE selesai = 0")
        jml_deadline = cursor.fetchone()[0]
        tanggal = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM jurnal WHERE tanggal = ?", (tanggal,))
        jml_jurnal = cursor.fetchone()[0]
        await query.edit_message_text(
            f"📚 *MENU PRODUKTIVITAS*\n\n"
            f"📅 Deadline aktif : *{jml_deadline}*\n"
            f"📔 Jurnal hari ini: *{jml_jurnal}* catatan\n\n"
            f"Pilih aksi:",
            reply_markup=kb_produktivitas(),
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

    # ── Aksi Produktivitas ─────────────────

    elif data == "aksi_jurnal":
        tanggal = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT isi FROM jurnal WHERE tanggal = ?", (tanggal,))
        rows = cursor.fetchall()
        if not rows:
            await query.edit_message_text(
                f"📔 Belum ada jurnal hari ini ({tanggal}).",
                reply_markup=kb_back("menu_produktivitas"),
            )
            return
        pesan = f"📔 *JURNAL {tanggal}*\n\n"
        for i, (isi,) in enumerate(rows, 1):
            pesan += f"{i}. {isi}\n"
        await query.edit_message_text(pesan, reply_markup=kb_back("menu_produktivitas"), parse_mode="Markdown")

    elif data == "aksi_tambah_jurnal":
        await query.edit_message_text(
            "📔 *TAMBAH JURNAL*\n\nKetik isi jurnal hari ini:\nContoh: `Hari ini belajar Python`",
            reply_markup=kb_back("menu_produktivitas"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "tambah_jurnal"

    elif data == "aksi_deadline":
        await query.edit_message_text(
            "📅 *TAMBAH DEADLINE*\n\nFormat:\n`Matkul | Tugas | YYYY-MM-DD`\n\nContoh:\n`AI | Makalah AI | 2026-06-30`",
            reply_markup=kb_back("menu_produktivitas"),
            parse_mode="Markdown",
        )
        context.user_data["mode"] = "tambah_deadline"

    elif data == "aksi_listdeadline":
        await _kirim_list_deadline_edit(query)

    elif data == "aksi_selesaideadline":
        cursor.execute("""
            SELECT id, tanggal, matkul, tugas
            FROM deadline_tugas WHERE selesai = 0 ORDER BY tanggal ASC
        """)
        rows = cursor.fetchall()
        if not rows:
            await query.edit_message_text(
                "📭 Tidak ada deadline aktif.",
                reply_markup=kb_back("menu_produktivitas"),
            )
            return
        pesan = "✅ *SELESAIKAN DEADLINE*\n\nKetik nomor ID deadline:\n\n"
        for row in rows:
            sisa = (datetime.strptime(row[1], "%Y-%m-%d") - datetime.now()).days
            pesan += f"ID {row[0]} — {row[2]} | {row[3]} | ⏳ {sisa} hari\n"
        await query.edit_message_text(pesan, reply_markup=kb_back("menu_produktivitas"), parse_mode="Markdown")
        context.user_data["mode"] = "selesai_deadline"

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
            "kat_makan":     "makan",
            "kat_transport": "transport",
            "kat_belanja":   "belanja",
            "kat_hiburan":   "hiburan",
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

    elif data == "aksi_rekap_bulan":
        await kirim_rekap_bulan(query)

    elif data == "aksi_progres":
        await _kirim_progres_edit(query)

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
    mode = context.user_data.get("mode")
    teks = update.message.text.strip()

    if not mode:
        await update.message.reply_text("Gunakan /start untuk membuka menu.")
        return

    # ── Tambah Jurnal ──────────────────────
    if mode == "tambah_jurnal":
        tanggal = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO jurnal (tanggal, isi) VALUES (?, ?)", (tanggal, teks))
        conn.commit()
        context.user_data.pop("mode")
        await update.message.reply_text(
            f"📔 Jurnal tersimpan!\n\n_{teks}_",
            parse_mode="Markdown",
            reply_markup=kb_produktivitas(),
        )

    # ── Tambah Deadline ────────────────────
    elif mode == "tambah_deadline":
        if "|" not in teks:
            await update.message.reply_text(
                "❌ Format salah.\nContoh: `AI | Makalah AI | 2026-06-30`",
                parse_mode="Markdown",
            )
            return
        bagian = teks.split("|")
        if len(bagian) != 3:
            await update.message.reply_text(
                "❌ Format salah.\nContoh: `AI | Makalah AI | 2026-06-30`",
                parse_mode="Markdown",
            )
            return
        matkul  = bagian[0].strip()
        tugas   = bagian[1].strip()
        tanggal = bagian[2].strip()
        try:
            datetime.strptime(tanggal, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "❌ Format tanggal salah. Gunakan YYYY-MM-DD.\nContoh: `2026-06-30`",
                parse_mode="Markdown",
            )
            return
        cursor.execute(
            "INSERT INTO deadline_tugas (tanggal, matkul, tugas) VALUES (?, ?, ?)",
            (tanggal, matkul, tugas),
        )
        conn.commit()
        context.user_data.pop("mode")
        await update.message.reply_text(
            f"📅 Deadline disimpan!\n\n"
            f"📚 *{matkul}*\n"
            f"📄 {tugas}\n"
            f"🗓️ {tanggal}",
            parse_mode="Markdown",
            reply_markup=kb_produktivitas(),
        )

    # ── Selesai Deadline ───────────────────
    elif mode == "selesai_deadline":
        try:
            id_tugas = int(teks)
            cursor.execute("SELECT id FROM deadline_tugas WHERE id = ? AND selesai = 0", (id_tugas,))
            row = cursor.fetchone()
            if not row:
                await update.message.reply_text("❌ ID tidak ditemukan. Coba lagi:")
                return
            cursor.execute("UPDATE deadline_tugas SET selesai = 1 WHERE id = ?", (id_tugas,))
            conn.commit()
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"✅ Deadline ID *{id_tugas}* ditandai selesai!",
                parse_mode="Markdown",
                reply_markup=kb_produktivitas(),
            )
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka ID. Coba lagi:")

    # ── Catat Uang (manual satu baris) ─────
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
            tanggal    = datetime.now().strftime("%Y-%m-%d")
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
            await update.message.reply_text(
                "❌ Nominal harus angka. Contoh: `makan 15000 nasi goreng`",
                parse_mode="Markdown",
            )

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
        tanggal    = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO pengeluaran (tanggal, kategori, nominal, keterangan) VALUES (?,?,?,?)",
            (tanggal, kategori, nominal, keterangan),
        )
        conn.commit()
        catat_histori(f"{kategori} Rp{nominal:,} - {keterangan}")
        context.user_data.pop("mode",      None)
        context.user_data.pop("kategori",  None)
        context.user_data.pop("nominal",   None)
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
            suhu       = d["main"]["temp"]
            kelembapan = d["main"]["humidity"]
            kondisi    = d["weather"][0]["description"]
            angin      = d["wind"]["speed"]
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
            bulan   = datetime.now().strftime("%Y-%m")
            cursor.execute("DELETE FROM target_tabungan WHERE bulan=?", (bulan,))
            cursor.execute(
                "INSERT INTO target_tabungan (target, bulan) VALUES (?,?)",
                (nominal, bulan),
            )
            conn.commit()
            context.user_data.pop("mode")
            await update.message.reply_text(
                f"🎯 Target bulan ini disimpan:\n*Rp {nominal:,}*",
                parse_mode="Markdown",
                reply_markup=kb_setting(),
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Masukkan angka saja. Contoh: `2000000`",
                parse_mode="Markdown",
            )

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
            await update.message.reply_text(
                "❌ Format jam salah. Gunakan HH:MM.\nContoh: `19:00`",
                parse_mode="Markdown",
            )
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
async def _kirim_list_deadline_edit(query):
    cursor.execute("""
        SELECT id, tanggal, matkul, tugas
        FROM deadline_tugas WHERE selesai = 0 ORDER BY tanggal ASC
    """)
    rows = cursor.fetchall()
    if not rows:
        await query.edit_message_text(
            "📭 Tidak ada deadline aktif.",
            reply_markup=kb_back("menu_produktivitas"),
        )
        return
    pesan = "📅 *DEADLINE AKTIF*\n\n"
    for row in rows:
        sisa = (datetime.strptime(row[1], "%Y-%m-%d") - datetime.now()).days
        pesan += (
            f"*ID {row[0]}*\n"
            f"📚 {row[2]}\n"
            f"📄 {row[3]}\n"
            f"🗓️ {row[1]} | ⏳ {sisa} hari lagi\n\n"
        )
    await query.edit_message_text(pesan, reply_markup=kb_back("menu_produktivitas"), parse_mode="Markdown")


async def _kirim_progres_edit(query):
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT target FROM target_tabungan
        WHERE bulan = ? ORDER BY id DESC LIMIT 1
    """, (bulan,))
    data = cursor.fetchone()
    if not data:
        await query.edit_message_text(
            "❌ Belum ada target bulan ini.\nSet target dulu via ⚙️ Pengaturan.",
            reply_markup=kb_back("menu_keuangan"),
        )
        return
    nilai_target = data[0]
    cursor.execute("""
        SELECT SUM(nominal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total  = cursor.fetchone()[0] or 0
    persen = (total / nilai_target * 100) if nilai_target > 0 else 0
    bar    = "█" * min(10, int(persen / 10)) + "░" * max(0, 10 - int(persen / 10))
    status = "✅ Masih aman" if total <= nilai_target else "❌ Over budget!"
    await query.edit_message_text(
        f"📈 *PROGRESS TARGET — {bulan}*\n\n"
        f"🎯 Target      : *Rp {nilai_target:,}*\n"
        f"💰 Pengeluaran : *Rp {total:,}*\n"
        f"📊 Progress    : `{bar}` {persen:.1f}%\n"
        f"📌 Status      : {status}",
        reply_markup=kb_back("menu_keuangan"),
        parse_mode="Markdown",
    )


async def _kirim_statistik_edit(query):
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT SUM(nominal), COUNT(*) FROM pengeluaran
        WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    row    = cursor.fetchone()
    total  = row[0] or 0
    jumlah = row[1] or 0

    if jumlah == 0:
        await query.edit_message_text(
            "📊 Belum ada data pengeluaran bulan ini.",
            reply_markup=kb_back_home(),
        )
        return

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml
        FROM pengeluaran
        WHERE substr(tanggal,1,7)=?
        GROUP BY kategori ORDER BY jml DESC LIMIT 5
    """, (bulan,))
    kat_rows = cursor.fetchall()

    rata   = total / max(1, datetime.now().day)
    tgt    = ambil_target()
    sisa   = tgt - total
    persen = round((total / tgt * 100), 1) if tgt > 0 else 0

    bar_isi = min(10, int(persen / 10))
    bar     = "█" * bar_isi + "░" * (10 - bar_isi)

    pesan  = f"📈 *STATISTIK BULAN {bulan}*\n\n"
    pesan += f"💸 Total Pengeluaran : *Rp {total:,}*\n"
    pesan += f"🧾 Jumlah Transaksi  : *{jumlah}*\n"
    pesan += f"📊 Rata-rata/hari    : *Rp {int(rata):,}*\n\n"
    pesan += f"🎯 Target Bulan      : *Rp {tgt:,}*\n"
    pesan += f"💰 Sisa Budget       : *Rp {sisa:,}*\n"
    pesan += f"📉 Terpakai          : `{bar}` {persen}%\n\n"
    pesan += "🏆 *Top Kategori:*\n"
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
    hari_ini = datetime.now().strftime("%Y-%m-%d")
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
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute(
        "SELECT SUM(nominal), COUNT(*) FROM pengeluaran WHERE substr(tanggal, 1, 7) = ?",
        (bulan,),
    )
    total, jumlah = cursor.fetchone()
    total  = total  or 0
    jumlah = jumlah or 0

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml
        FROM pengeluaran
        WHERE substr(tanggal, 1, 7) = ?
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

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)

    await query.message.reply_photo(
        photo=buf,
        caption="📊 *Grafik Pengeluaran per Kategori*",
        parse_mode="Markdown",
        reply_markup=kb_back("menu_keuangan"),
    )


# ==========================================
# V2.7 — REKAP BULANAN (dari tombol)
# ==========================================
async def kirim_rekap_bulan(query):
    bulan = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT SUM(nominal), COUNT(*)
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    row    = cursor.fetchone()
    total  = row[0] or 0
    jumlah = row[1] or 0

    if jumlah == 0:
        await query.edit_message_text(
            f"📭 Tidak ada data pengeluaran untuk bulan *{bulan}*.",
            reply_markup=kb_back("menu_keuangan"),
            parse_mode="Markdown",
        )
        return

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml, COUNT(*) as cnt
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        GROUP BY kategori ORDER BY jml DESC
    """, (bulan,))
    kat_rows = cursor.fetchall()

    cursor.execute("""
        SELECT tanggal, SUM(nominal) as jml
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        GROUP BY tanggal ORDER BY jml DESC LIMIT 1
    """, (bulan,))
    hari_boros = cursor.fetchone()

    cursor.execute("""
        SELECT nominal, keterangan, kategori, tanggal
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        ORDER BY nominal DESC LIMIT 1
    """, (bulan,))
    transaksi_terbesar = cursor.fetchone()

    cursor.execute("""
        SELECT target FROM target_tabungan WHERE bulan=? ORDER BY id DESC LIMIT 1
    """, (bulan,))
    target_row   = cursor.fetchone()
    nilai_target = target_row[0] if target_row else 0
    sisa         = nilai_target - total
    persen       = round(total / nilai_target * 100, 1) if nilai_target > 0 else 0
    bar          = "█" * min(10, int(persen / 10)) + "░" * max(0, 10 - int(persen / 10))

    cursor.execute("""
        SELECT COUNT(*) FROM deadline_tugas WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total_deadline = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM deadline_tugas WHERE substr(tanggal,1,7)=? AND selesai=1
    """, (bulan,))
    deadline_selesai = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM jurnal WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total_jurnal = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT tanggal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    hari_aktif  = cursor.fetchone()[0] or 1
    rata_harian = total // hari_aktif

    pesan  = f"📊 *REKAP BULANAN — {bulan}*\n"
    pesan += "━━━━━━━━━━━━━━━━━━━━\n\n"

    pesan += "💸 *PENGELUARAN*\n"
    pesan += f"   Total       : Rp {total:,}\n"
    pesan += f"   Transaksi   : {jumlah}x\n"
    pesan += f"   Hari aktif  : {hari_aktif} hari\n"
    pesan += f"   Rata-rata   : Rp {rata_harian:,}/hari\n\n"

    pesan += "🎯 *TARGET*\n"
    if nilai_target > 0:
        status = "✅ HEMAT" if sisa >= 0 else "❌ OVER BUDGET"
        pesan += f"   Target      : Rp {nilai_target:,}\n"
        pesan += f"   Terpakai    : `{bar}` {persen}%\n"
        pesan += f"   Sisa        : Rp {sisa:,}\n"
        pesan += f"   Status      : {status}\n\n"
    else:
        pesan += "   Tidak ada target bulan ini\n\n"

    pesan += "🏷️ *PER KATEGORI*\n"
    for k, v, c in kat_rows:
        pct  = round(v / total * 100, 1) if total > 0 else 0
        pesan += f"   • {k}: Rp {v:,} ({c}x, {pct}%)\n"
    pesan += "\n"

    if hari_boros:
        pesan += "📅 *HARI PALING BOROS*\n"
        pesan += f"   {hari_boros[0]} — Rp {hari_boros[1]:,}\n\n"

    if transaksi_terbesar:
        pesan += "💣 *TRANSAKSI TERBESAR*\n"
        pesan += (
            f"   Rp {transaksi_terbesar[0]:,}\n"
            f"   {transaksi_terbesar[2]} — {transaksi_terbesar[1]}\n"
            f"   📅 {transaksi_terbesar[3]}\n\n"
        )

    pesan += "📅 *DEADLINE*\n"
    pesan += f"   Total    : {total_deadline}\n"
    pesan += f"   Selesai  : {deadline_selesai}\n"
    pesan += f"   Sisa     : {total_deadline - deadline_selesai}\n\n"

    pesan += "📔 *JURNAL*\n"
    pesan += f"   {total_jurnal} catatan bulan ini\n"

    await query.edit_message_text(pesan, reply_markup=kb_back("menu_keuangan"), parse_mode="Markdown")


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
    )


async def cmd_uang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Contoh: `/uang makan 15000 nasi goreng`", parse_mode="Markdown")
        return
    try:
        kategori   = context.args[0]
        nominal    = int(context.args[1])
        keterangan = " ".join(context.args[2:])
        tanggal    = datetime.now().strftime("%Y-%m-%d")
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


async def target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Contoh:\n/target 3000000")
        return
    target_uang = int(context.args[0])
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute("DELETE FROM target_tabungan WHERE bulan=?", (bulan,))
    cursor.execute(
        "INSERT INTO target_tabungan (target, bulan) VALUES (?,?)",
        (target_uang, bulan)
    )
    conn.commit()
    await update.message.reply_text(f"🎯 Target bulan ini:\nRp {target_uang:,}")


async def jurnal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isi = " ".join(context.args)
    if not isi:
        await update.message.reply_text("Contoh:\n/jurnal Hari ini belajar Railway")
        return
    tanggal = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO jurnal (tanggal, isi) VALUES (?,?)", (tanggal, isi))
    conn.commit()
    await update.message.reply_text("📔 Jurnal tersimpan.")


async def jurnal_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tanggal = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT isi FROM jurnal WHERE tanggal=?", (tanggal,))
    data = cursor.fetchall()
    if not data:
        await update.message.reply_text("Belum ada jurnal hari ini.")
        return
    pesan = "📔 Jurnal Hari Ini\n\n"
    for i, item in enumerate(data):
        pesan += f"{i+1}. {item[0]}\n"
    await update.message.reply_text(pesan)


async def progres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bulan = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT target FROM target_tabungan
        WHERE bulan = ? ORDER BY id DESC LIMIT 1
    """, (bulan,))
    data = cursor.fetchone()
    if not data:
        await update.message.reply_text("Belum ada target bulan ini.")
        return
    nilai_target = data[0]
    cursor.execute("""
        SELECT SUM(nominal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total  = cursor.fetchone()[0] or 0
    persen = (total / nilai_target * 100) if nilai_target > 0 else 0
    await update.message.reply_text(
        f"🎯 Target : Rp {nilai_target:,}\n"
        f"💰 Pengeluaran : Rp {total:,}\n"
        f"📈 Progress : {persen:.1f}%"
    )


async def deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teks = update.message.text.replace("/deadline", "").strip()
    if "|" not in teks:
        await update.message.reply_text(
            "Format:\n/deadline Matkul | Tugas | YYYY-MM-DD\n\n"
            "Contoh:\n/deadline AI | Makalah AI | 2026-06-30"
        )
        return
    bagian = teks.split("|")
    if len(bagian) != 3:
        await update.message.reply_text("Format salah.\n/deadline Matkul | Tugas | YYYY-MM-DD")
        return
    matkul  = bagian[0].strip()
    tugas   = bagian[1].strip()
    tanggal = bagian[2].strip()
    cursor.execute(
        "INSERT INTO deadline_tugas (tanggal, matkul, tugas) VALUES (?, ?, ?)",
        (tanggal, matkul, tugas)
    )
    conn.commit()
    await update.message.reply_text(
        f"📅 Deadline disimpan\n\n"
        f"📚 {matkul}\n"
        f"📄 {tugas}\n"
        f"🗓️ {tanggal}"
    )


async def listdeadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT id, tanggal, matkul, tugas
        FROM deadline_tugas WHERE selesai = 0 ORDER BY tanggal ASC
    """)
    data = cursor.fetchall()
    if not data:
        await update.message.reply_text("📭 Tidak ada deadline.")
        return
    pesan = "📅 Deadline Aktif\n\n"
    for item in data:
        sisa = (datetime.strptime(item[1], "%Y-%m-%d") - datetime.now()).days
        pesan += (
            f"{item[0]}.\n"
            f"📚 {item[2]}\n"
            f"📄 {item[3]}\n"
            f"🗓️ {item[1]}\n"
            f"⏳ {sisa} hari lagi\n\n"
        )
    await update.message.reply_text(pesan)


async def selesaideadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Contoh:\n/selesaideadline 1")
        return
    id_tugas = context.args[0]
    cursor.execute("UPDATE deadline_tugas SET selesai = 1 WHERE id = ?", (id_tugas,))
    conn.commit()
    await update.message.reply_text("✅ Deadline ditandai selesai.")


async def cek_deadline(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT id, tanggal, matkul, tugas
        FROM deadline_tugas WHERE selesai = 0
    """)
    data = cursor.fetchall()
    if not data:
        return
    for item in data:
        tanggal = item[1]
        matkul  = item[2]
        tugas   = item[3]
        try:
            sisa_hari = (datetime.strptime(tanggal, "%Y-%m-%d") - datetime.now()).days
            if 0 <= sisa_hari <= 3:
                await context.bot.send_message(
                    chat_id=CHAT_ID_KAMU,
                    text=(
                        "⚠️ DEADLINE MENDEKAT\n\n"
                        f"📚 {matkul}\n"
                        f"📄 {tugas}\n"
                        f"🗓️ {tanggal}\n"
                        f"⏳ Tinggal {sisa_hari} hari lagi"
                    )
                )
        except Exception:
            pass


async def dashboard_pagi(context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT COUNT(*) FROM tugas")
        total_tugas = cursor.fetchone()[0]

        cursor.execute("""
            SELECT matkul, tugas, tanggal FROM deadline_tugas
            WHERE selesai = 0 ORDER BY tanggal ASC LIMIT 1
        """)
        deadline_row = cursor.fetchone()
        teks_deadline = "Tidak ada deadline"
        if deadline_row:
            matkul    = deadline_row[0]
            tugas_d   = deadline_row[1]
            tanggal   = deadline_row[2]
            sisa_hari = (datetime.strptime(tanggal, "%Y-%m-%d") - datetime.now()).days
            teks_deadline = f"{matkul}\n📄 {tugas_d}\n⏳ {sisa_hari} hari lagi"

        bulan = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            SELECT SUM(nominal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
        """, (bulan,))
        total_pengeluaran = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT target FROM target_tabungan WHERE bulan = ? ORDER BY id DESC LIMIT 1
        """, (bulan,))
        hasil_target = cursor.fetchone()
        teks_target  = "Belum ada target"
        if hasil_target:
            nilai_target = hasil_target[0]
            persen       = (total_pengeluaran / nilai_target * 100) if nilai_target > 0 else 0
            teks_target  = f"Rp {nilai_target:,}\n📈 {persen:.1f}%"

        hari_ini = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM jurnal WHERE tanggal = ?", (hari_ini,))
        jumlah_jurnal = cursor.fetchone()[0]

        pesan = (
            "🌅 SELAMAT PAGI BAGAS\n\n"
            f"📋 Tugas Aktif\n{total_tugas} tugas\n\n"
            f"📅 Deadline Terdekat\n{teks_deadline}\n\n"
            f"💰 Pengeluaran\nRp {total_pengeluaran:,}\n\n"
            f"🎯 Target Tabungan\n{teks_target}\n\n"
            f"📔 Jurnal Hari Ini\n{jumlah_jurnal} catatan\n\n"
            "🚀 Semangat hari ini!"
        )
        await context.bot.send_message(chat_id=CHAT_ID_KAMU, text=pesan)
    except Exception as e:
        print("ERROR DASHBOARD PAGI:", e)


async def statistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cursor.execute("SELECT COUNT(*) FROM tugas")
        total_tugas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM deadline_tugas WHERE selesai = 0")
        total_deadline = cursor.fetchone()[0]

        bulan = datetime.now().strftime("%Y-%m")
        cursor.execute("""
            SELECT SUM(nominal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
        """, (bulan,))
        total_pengeluaran = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT target FROM target_tabungan WHERE bulan = ? ORDER BY id DESC LIMIT 1
        """, (bulan,))
        hasil_target = cursor.fetchone()
        teks_target  = "Belum ada target"
        progress     = 0
        nilai_target = 0
        if hasil_target:
            nilai_target = hasil_target[0]
            progress     = (total_pengeluaran / nilai_target * 100) if nilai_target > 0 else 0
            teks_target  = f"Rp {nilai_target:,}"

        cursor.execute("SELECT COUNT(*) FROM jurnal")
        total_jurnal = cursor.fetchone()[0]

        pesan = (
            "📊 Statistik MyAiku\n\n"
            f"📋 Tugas Aktif\n{total_tugas}\n\n"
            f"📅 Deadline Aktif\n{total_deadline}\n\n"
            f"💰 Total Pengeluaran\nRp {total_pengeluaran:,}\n\n"
            f"🎯 Target Tabungan\n{teks_target}\n\n"
            f"📈 Progress Target\n{progress:.1f}%\n\n"
            f"📔 Total Jurnal\n{total_jurnal}\n\n"
            "🚀 Tetap semangat!"
        )
        await update.message.reply_text(pesan)
    except Exception as e:
        await update.message.reply_text(f"Error:\n{e}")


# ==========================================
# V2.7 — REKAP BULANAN (command /rekapbulan)
# ==========================================
async def rekapbulan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /rekapbulan          → rekap bulan ini
    /rekapbulan 2025-05  → rekap bulan tertentu
    """
    if context.args:
        bulan = context.args[0]
        try:
            datetime.strptime(bulan, "%Y-%m")
        except ValueError:
            await update.message.reply_text(
                "❌ Format bulan salah.\nContoh: `/rekapbulan 2025-05`",
                parse_mode="Markdown",
            )
            return
    else:
        bulan = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT SUM(nominal), COUNT(*) FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    row    = cursor.fetchone()
    total  = row[0] or 0
    jumlah = row[1] or 0

    if jumlah == 0:
        await update.message.reply_text(
            f"📭 Tidak ada data pengeluaran untuk bulan *{bulan}*.",
            parse_mode="Markdown",
        )
        return

    cursor.execute("""
        SELECT kategori, SUM(nominal) as jml, COUNT(*) as cnt
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        GROUP BY kategori ORDER BY jml DESC
    """, (bulan,))
    kat_rows = cursor.fetchall()

    cursor.execute("""
        SELECT tanggal, SUM(nominal) as jml
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        GROUP BY tanggal ORDER BY jml DESC LIMIT 1
    """, (bulan,))
    hari_boros = cursor.fetchone()

    cursor.execute("""
        SELECT nominal, keterangan, kategori, tanggal
        FROM pengeluaran WHERE substr(tanggal,1,7)=?
        ORDER BY nominal DESC LIMIT 1
    """, (bulan,))
    transaksi_terbesar = cursor.fetchone()

    cursor.execute("""
        SELECT target FROM target_tabungan WHERE bulan=? ORDER BY id DESC LIMIT 1
    """, (bulan,))
    target_row   = cursor.fetchone()
    nilai_target = target_row[0] if target_row else 0
    sisa         = nilai_target - total
    persen       = round(total / nilai_target * 100, 1) if nilai_target > 0 else 0
    bar          = "█" * min(10, int(persen / 10)) + "░" * max(0, 10 - int(persen / 10))

    cursor.execute("""
        SELECT COUNT(*) FROM deadline_tugas WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total_deadline = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM deadline_tugas WHERE substr(tanggal,1,7)=? AND selesai=1
    """, (bulan,))
    deadline_selesai = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM jurnal WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    total_jurnal = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT tanggal) FROM pengeluaran WHERE substr(tanggal,1,7)=?
    """, (bulan,))
    hari_aktif  = cursor.fetchone()[0] or 1
    rata_harian = total // hari_aktif

    pesan  = f"📊 *REKAP BULANAN — {bulan}*\n"
    pesan += "━━━━━━━━━━━━━━━━━━━━\n\n"

    pesan += "💸 *PENGELUARAN*\n"
    pesan += f"   Total       : Rp {total:,}\n"
    pesan += f"   Transaksi   : {jumlah}x\n"
    pesan += f"   Hari aktif  : {hari_aktif} hari\n"
    pesan += f"   Rata-rata   : Rp {rata_harian:,}/hari\n\n"

    pesan += "🎯 *TARGET*\n"
    if nilai_target > 0:
        status = "✅ HEMAT" if sisa >= 0 else "❌ OVER BUDGET"
        pesan += f"   Target      : Rp {nilai_target:,}\n"
        pesan += f"   Terpakai    : `{bar}` {persen}%\n"
        pesan += f"   Sisa        : Rp {sisa:,}\n"
        pesan += f"   Status      : {status}\n\n"
    else:
        pesan += "   Tidak ada target bulan ini\n\n"

    pesan += "🏷️ *PER KATEGORI*\n"
    for k, v, c in kat_rows:
        pct  = round(v / total * 100, 1) if total > 0 else 0
        pesan += f"   • {k}: Rp {v:,} ({c}x, {pct}%)\n"
    pesan += "\n"

    if hari_boros:
        pesan += "📅 *HARI PALING BOROS*\n"
        pesan += f"   {hari_boros[0]} — Rp {hari_boros[1]:,}\n\n"

    if transaksi_terbesar:
        pesan += "💣 *TRANSAKSI TERBESAR*\n"
        pesan += (
            f"   Rp {transaksi_terbesar[0]:,}\n"
            f"   {transaksi_terbesar[2]} — {transaksi_terbesar[1]}\n"
            f"   📅 {transaksi_terbesar[3]}\n\n"
        )

    pesan += "📅 *DEADLINE*\n"
    pesan += f"   Total    : {total_deadline}\n"
    pesan += f"   Selesai  : {deadline_selesai}\n"
    pesan += f"   Sisa     : {total_deadline - deadline_selesai}\n\n"

    pesan += "📔 *JURNAL*\n"
    pesan += f"   {total_jurnal} catatan bulan ini\n"

    await update.message.reply_text(pesan, parse_mode="Markdown")


# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    init_db()
    print("✅ Database SQLite siap.")
    print("🤖 Bot V2.7.1 menyala...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",           start))
    app.add_handler(CommandHandler("tugas",           cmd_tugas))
    app.add_handler(CommandHandler("uang",            cmd_uang))
    app.add_handler(CommandHandler("cuaca",           cmd_cuaca))
    app.add_handler(CommandHandler("target",          target))
    app.add_handler(CommandHandler("progres",         progres))
    app.add_handler(CommandHandler("jurnal",          jurnal))
    app.add_handler(CommandHandler("jurnalhariini",   jurnal_hari_ini))
    app.add_handler(CommandHandler("deadline",        deadline))
    app.add_handler(CommandHandler("listdeadline",    listdeadline))
    app.add_handler(CommandHandler("selesaideadline", selesaideadline))
    app.add_handler(CommandHandler("statistik",       statistik))
    app.add_handler(CommandHandler("rekapbulan",      rekapbulan))

    app.add_handler(CallbackQueryHandler(router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, teks_handler))

    wib = pytz.timezone("Asia/Jakarta")

    app.job_queue.run_repeating(cek_pengingat, interval=60, first=10)
    app.job_queue.run_daily(cek_deadline,   time=time(hour=5, minute=0, tzinfo=wib))
    app.job_queue.run_daily(dashboard_pagi, time=time(hour=5, minute=5, tzinfo=wib))

    app.run_polling()