import random

# Funzione che simula le statistiche di una partita (per ora)
def get_match_stats():
    return {
        "minute": random.randint(60, 95),
        "shots": random.randint(5, 20),
        "corners": random.randint(1, 12),
        "dangerous_attacks": random.randint(10, 70)
    }

# Funzione che decide se inviare un segnale
def check_signal():
    stats = get_match_stats()

    if (
        stats["minute"] >= 75 and
        stats["shots"] >= 12 and
        stats["dangerous_attacks"] >= 40
    ):
        return f"""
📢 *Segnale LIVE*  
⏱ Minuto: {stats['minute']}
🎯 Tiri: {stats['shots']}
⛳ Corner: {stats['corners']}
⚠️ Attacchi Pericolosi: {stats['dangerous_attacks']}
💥 Probabilità Gol: *ALTA*
"""

    return None
