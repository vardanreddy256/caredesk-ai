import sqlite3
import os
import re

from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path


DB = Path(
    os.getenv(
        "DATABASE_PATH",
        str(Path(__file__).with_name("care.db"))
    )
)


# Database connection
@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=10)

    try:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")

        yield c

        c.commit()

    except Exception:
        c.rollback()
        raise

    finally:
        c.close()


# Initialize database and mock data
def init():
    with connect() as c:

        c.executescript("""
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY,
                name TEXT,
                specialty TEXT
            );

            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY,
                doctor_id INTEGER REFERENCES doctors(id),
                day TEXT,
                time TEXT,
                UNIQUE(doctor_id, day, time)
            );

            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY,
                slot_id INTEGER REFERENCES slots(id),
                phone TEXT,
                status TEXT DEFAULT 'confirmed'
            );

            CREATE UNIQUE INDEX IF NOT EXISTS one_booking
            ON appointments(slot_id)
            WHERE status = 'confirmed';
        """)

        doctors = [
            (1, "Dr. Ananya Sharma", "Cardiology"),
            (2, "Dr. Arjun Mehta", "General Medicine"),
            (3, "Dr. Priya Rao", "Dermatology"),
            (4, "Dr. Neha Iyer", "Pediatrics")
        ]

        c.executemany(
            "INSERT OR IGNORE INTO doctors VALUES (?, ?, ?)",
            doctors
        )

        today = datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).date()

        slots = [
            (
                doctor_id,
                str(today + timedelta(days=day)),
                time
            )
            for doctor_id in range(1, 5)
            for day in range(1, 8)
            for time in ("09:30", "11:00", "14:00")
        ]

        c.executemany(
            """
            INSERT OR IGNORE INTO slots
            (doctor_id, day, time)
            VALUES (?, ?, ?)
            """,
            slots
        )


# Check doctor availability
def availability(doctor="", date=""):
    with connect() as c:

        rows = c.execute(
            """
            SELECT
                s.id AS slot_id,
                d.name,
                d.specialty,
                s.day,
                s.time

            FROM slots s

            JOIN doctors d
                ON d.id = s.doctor_id

            WHERE
                (d.name LIKE ? OR d.specialty LIKE ?)

                AND s.day >= ?

                AND (? = '' OR s.day = ?)

                AND NOT EXISTS (
                    SELECT 1
                    FROM appointments a
                    WHERE a.slot_id = s.id
                    AND a.status = 'confirmed'
                )

            ORDER BY s.day, s.time
            """,
            (
                f"%{doctor}%",
                f"%{doctor}%",
                str(
                    datetime.now(
                        ZoneInfo("Asia/Kolkata")
                    ).date()
                ),
                date,
                date
            )
        )

        return [dict(row) for row in rows]


# Validate and normalize phone number
def phone_number(value):
    n = re.sub(r"[^0-9]", "", value)

    if len(n) == 12 and n.startswith("91"):
        n = n[2:]

    if len(n) != 10:
        raise ValueError(
            "Please provide a ten digit Indian phone number."
        )

    return n


# Book an appointment
def book(slot_id, phone):
    phone = phone_number(phone)

    try:
        with connect() as c:

            c.execute("BEGIN IMMEDIATE")

            slot = c.execute(
                "SELECT * FROM slots WHERE id = ?",
                (slot_id,)
            ).fetchone()

            current_time = datetime.now(
                ZoneInfo("Asia/Kolkata")
            ).strftime("%Y-%m-%d %H:%M")

            if (
                not slot
                or f"{slot['day']} {slot['time']}" <= current_time
            ):
                return {
                    "error": "Invalid or expired slot"
                }

            appointment = c.execute(
                """
                INSERT INTO appointments
                (slot_id, phone)
                VALUES (?, ?)
                """,
                (slot_id, phone)
            )

            return {
                "status": "confirmed",
                "appointment_id": appointment.lastrowid,
                "slot_id": slot_id
            }

    except sqlite3.IntegrityError:
        return {
            "error": "Slot already booked"
        }


# Get appointments
def appointments(phone=None):
    with connect() as c:

        rows = c.execute(
            """
            SELECT
                a.id,
                a.phone,
                a.status,
                d.name,
                s.day,
                s.time

            FROM appointments a

            JOIN slots s
                ON s.id = a.slot_id

            JOIN doctors d
                ON d.id = s.doctor_id

            WHERE (? IS NULL OR a.phone = ?)

            ORDER BY a.id DESC
            """,
            (phone, phone)
        )

        return [dict(row) for row in rows]


# Cancel an appointment
def cancel(phone, appointment_id=None):
    phone = phone_number(phone)

    with connect() as c:

        c.execute("BEGIN IMMEDIATE")

        matches = [
            dict(row)
            for row in c.execute(
                """
                SELECT id, slot_id
                FROM appointments
                WHERE phone = ?
                AND status = 'confirmed'
                """,
                (phone,)
            )
        ]

        if appointment_id is None and len(matches) != 1:

            return {
                "status": (
                    "choose_appointment"
                    if matches
                    else "not_found"
                ),
                "appointments": [
                    appointment
                    for appointment in appointments(phone)
                    if appointment["status"] == "confirmed"
                ]
            }

        target = (
            appointment_id
            if appointment_id is not None
            else matches[0]["id"]
        )

        result = c.execute(
            """
            UPDATE appointments
            SET status = 'cancelled'
            WHERE id = ?
            AND phone = ?
            AND status = 'confirmed'
            """,
            (target, phone)
        )

        return {
            "status": (
                "cancelled"
                if result.rowcount
                else "not_found"
            ),
            "appointment_id": target
        }