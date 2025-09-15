#!/usr/bin/env python3
"""
Script per generare dati di test realistici per la leaderboard.

Questo script è fondamentale per i test di performance - genera grandi quantità
di dati che simulano un gioco reale con migliaia o milioni di utenti.

Utilizzo:
    python populate_data.py --users 10000    # Genera 10.000 utenti
    python populate_data.py --users 100000 --distribution skewed  # Distribuzione più realistica
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta
from typing import List, Tuple

import psycopg2
import numpy as np
from tqdm import tqdm


class DataGenerator:
    """
    Classe che genera dati realistici per il test della leaderboard.

    Simula diversi tipi di distribuzione dei punteggi che potresti trovare
    in un gioco reale, dove pochi giocatori sono molto bravi e molti sono nella media.
    """

    def __init__(self, db_config: dict):
        """
        Inizializza il generatore con la configurazione del database.

        Args:
            db_config: Dizionario con host, database, user, password
        """
        self.db_config = db_config
        self.connection = None

    def connect(self):
        """Stabilisce la connessione al database PostgreSQL."""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.connection.autocommit = False  # Usiamo transazioni manuali per performance
            print(f"✅ Connesso al database {self.db_config['database']}")
        except Exception as e:
            print(f"❌ Errore connessione database: {e}")
            sys.exit(1)

    def disconnect(self):
        """Chiude la connessione al database."""
        if self.connection:
            self.connection.close()
            print("🔌 Connessione database chiusa")

    def generate_usernames(self, count: int) -> List[str]:
        """
        Genera nomi utente realistici e univoci.

        Args:
            count: Numero di username da generare

        Returns:
            Lista di username univoci
        """
        print(f"🎲 Generando {count} username...")

        # Parti comuni per nomi utente realistici
        prefixes = ["Player", "Gamer", "Pro", "Master", "Noob", "Elite", "Super", "Mega", "Ultra", "Alpha"]
        suffixes = ["2023", "Gaming", "XD", "Pro", "Best", "King", "Queen", "Star", "Hero", "Legend"]

        usernames = set()  # Usa set per garantire unicità
        attempts = 0
        max_attempts = count * 10  # Limite per evitare loop infiniti

        with tqdm(total=count, desc="Generando username") as pbar:
            while len(usernames) < count and attempts < max_attempts:
                attempts += 1

                # Mix di strategie per variety
                if attempts % 3 == 0:
                    # Formato: Prefix + numero
                    username = f"{random.choice(prefixes)}{random.randint(1, 99999)}"
                elif attempts % 3 == 1:
                    # Formato: Prefix + Suffix + numero
                    username = f"{random.choice(prefixes)}{random.choice(suffixes)}{random.randint(1, 999)}"
                else:
                    # Formato: Username + numero incrementale per garantire unicità
                    username = f"User{len(usernames)+1}_{random.randint(100, 99999)}"

                if username not in usernames:
                    usernames.add(username)
                    pbar.update(1)

        if len(usernames) < count:
            raise ValueError(f"Impossibile generare {count} username univoci dopo {max_attempts} tentativi")

        return list(usernames)

    def generate_scores(self, count: int, distribution: str = "normal") -> List[int]:
        """
        Genera punteggi con diverse distribuzioni statistiche.

        Questo è IL PUNTO CHIAVE: diversi giochi hanno diverse distribuzioni di punteggi.
        Testare con distribuzioni realistiche ci dà risultati più credibili.

        Args:
            count: Numero di punteggi da generare
            distribution: Tipo di distribuzione ("normal", "skewed", "uniform", "exponential")

        Returns:
            Lista di punteggi
        """
        print(f"📊 Generando {count} punteggi con distribuzione '{distribution}'...")

        if distribution == "normal":
            # Distribuzione normale: la maggior parte degli utenti ha punteggi medi
            # Media: 1000, Deviazione standard: 300
            scores = np.random.normal(1000, 300, count)

        elif distribution == "skewed":
            # Distribuzione "skewed": pochi utenti con punteggi altissimi, molti bassi
            # Questo simula giochi competitivi dove essere bravi è difficile
            base_scores = np.random.exponential(500, count)  # La maggior parte tra 0-1500
            # Aggiungiamo alcuni "pro players" con punteggi molto alti
            num_pros = max(1, count // 100)  # 1% di pro players
            pro_indices = random.sample(range(count), num_pros)
            for idx in pro_indices:
                base_scores[idx] += random.randint(5000, 15000)  # Pro players: 5K-15K punti extra
            scores = base_scores

        elif distribution == "uniform":
            # Distribuzione uniforme: tutti i punteggi ugualmente probabili
            # Utile per test "artificiali" ma poco realistico
            scores = np.random.uniform(0, 5000, count)

        elif distribution == "exponential":
            # Distribuzione esponenziale: molti punteggi bassi, pochi alti
            # Simula giochi dove è facile iniziare ma difficile eccellere
            scores = np.random.exponential(800, count)

        else:
            raise ValueError(f"Distribuzione '{distribution}' non supportata")

        # Convertiamo in interi e assicuriamoci che siano >= 0
        scores = np.maximum(0, scores.astype(int))

        print(f"📈 Statistiche punteggi:")
        print(f"   Min: {np.min(scores)}")
        print(f"   Max: {np.max(scores)}")
        print(f"   Media: {np.mean(scores):.1f}")
        print(f"   Mediana: {np.median(scores):.1f}")
        print(f"   Dev.Standard: {np.std(scores):.1f}")

        return scores.tolist()

    def insert_users_batch(self, usernames: List[str], batch_size: int = 1000):
        """
        Inserisce gli utenti nel database a "batch" per efficienza.

        PERFORMANCE TIP: Inserire 1000 record alla volta è molto più veloce
        che inserirne uno per uno. Con 100K utenti, la differenza è drammatica!

        Args:
            usernames: Lista di nomi utente
            batch_size: Quanti record inserire per transazione
        """
        cursor = self.connection.cursor()
        total_users = len(usernames)

        print(f"👥 Inserendo {total_users} utenti (batch da {batch_size})...")

        # Prepariamo i dati per l'inserimento batch
        user_data = []
        for i, username in enumerate(usernames):
            # Data di registrazione casuale negli ultimi 365 giorni
            reg_date = datetime.now() - timedelta(days=random.randint(1, 365))
            # 95% degli utenti attivi (simula la realtà)
            is_active = random.random() < 0.95

            user_data.append((
                username,
                f"{username.lower()}@test.com",
                reg_date,
                is_active
            ))

        # Inserimento a batch per performance
        for i in tqdm(range(0, total_users, batch_size), desc="Inserendo utenti"):
            batch = user_data[i:i + batch_size]

            try:
                # Query preparata per inserimento multiplo
                cursor.executemany("""
                    INSERT INTO users (username, email, registration_date, is_active)
                    VALUES (%s, %s, %s, %s)
                """, batch)

                # Commit ogni batch per non tenere troppi dati in memoria
                self.connection.commit()

            except Exception as e:
                print(f"❌ Errore inserimento batch {i}: {e}")
                self.connection.rollback()
                raise

        cursor.close()
        print(f"✅ {total_users} utenti inseriti con successo")

    def insert_leaderboard_batch(self, scores: List[int], batch_size: int = 1000):
        """
        Inserisce i punteggi nella leaderboard.

        Args:
            scores: Lista di punteggi (deve corrispondere agli user_id)
            batch_size: Dimensione del batch
        """
        cursor = self.connection.cursor()
        total_scores = len(scores)

        print(f"🏆 Inserendo {total_scores} punteggi nella leaderboard...")

        # Prepariamo i dati: ogni punteggio è associato a user_id sequenziale
        leaderboard_data = []
        for i, score in enumerate(scores):
            user_id = i + 1  # Gli user_id iniziano da 1 (SERIAL)
            games_played = random.randint(1, 100)  # Numero casuale di partite

            leaderboard_data.append((user_id, score, games_played))

        # Inserimento a batch
        for i in tqdm(range(0, total_scores, batch_size), desc="Inserendo punteggi"):
            batch = leaderboard_data[i:i + batch_size]

            try:
                cursor.executemany("""
                    INSERT INTO leaderboard (user_id, score, games_played)
                    VALUES (%s, %s, %s)
                """, batch)

                self.connection.commit()

            except Exception as e:
                print(f"❌ Errore inserimento leaderboard batch {i}: {e}")
                self.connection.rollback()
                raise

        cursor.close()
        print(f"✅ {total_scores} punteggi inseriti nella leaderboard")

    def get_current_stats(self):
        """Mostra statistiche attuali del database per verifica."""
        cursor = self.connection.cursor()

        # Conta utenti totali e attivi
        cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_active) FROM users")
        total_users, active_users = cursor.fetchone()

        # Conta record nella leaderboard
        cursor.execute("SELECT COUNT(*) FROM leaderboard")
        leaderboard_count = cursor.fetchone()[0]

        # Statistiche punteggi
        cursor.execute("SELECT MIN(score), MAX(score), AVG(score), STDDEV(score) FROM leaderboard")
        min_score, max_score, avg_score, stddev_score = cursor.fetchone()

        cursor.close()

        print("\n📊 STATISTICHE DATABASE:")
        print(f"   Utenti totali: {total_users:,}")
        print(f"   Utenti attivi: {active_users:,}")
        print(f"   Record leaderboard: {leaderboard_count:,}")
        print(f"   Punteggio min: {min_score}")
        print(f"   Punteggio max: {max_score}")
        print(f"   Punteggio medio: {avg_score:.1f}")
        if stddev_score:
            print(f"   Deviazione standard: {stddev_score:.1f}")


def main():
    """Funzione principale che gestisce gli argomenti da riga di comando."""
    parser = argparse.ArgumentParser(
        description="Genera dati di test per la leaderboard PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  python populate_data.py --users 1000                    # 1K utenti, distribuzione normale
  python populate_data.py --users 50000 --dist skewed     # 50K utenti, pochi top players
  python populate_data.py --users 100000 --batch 2000     # 100K utenti, batch da 2000
        """
    )

    parser.add_argument(
        '--users', '-u',
        type=int,
        required=True,
        help='Numero di utenti da generare'
    )

    parser.add_argument(
        '--distribution', '--dist',
        choices=['normal', 'skewed', 'uniform', 'exponential'],
        default='normal',
        help='Tipo di distribuzione dei punteggi (default: normal)'
    )

    parser.add_argument(
        '--batch-size', '--batch',
        type=int,
        default=1000,
        help='Dimensione del batch per inserimento (default: 1000)'
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Cancella tutti i dati esistenti prima di generare nuovi dati'
    )

    args = parser.parse_args()

    # Configurazione database (usa variabili d'ambiente se disponibili)
    import os
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'leaderboard_test'),
        'user': os.getenv('DB_USER', 'testuser'),
        'password': os.getenv('DB_PASSWORD', 'testpass123'),
        'port': int(os.getenv('DB_PORT', 5432))
    }

    print("🚀 GENERATORE DATI LEADERBOARD")
    print(f"   Utenti da generare: {args.users:,}")
    print(f"   Distribuzione punteggi: {args.distribution}")
    print(f"   Dimensione batch: {args.batch_size}")

    # Inizializza il generatore
    generator = DataGenerator(db_config)

    try:
        start_time = time.time()

        generator.connect()

        # Opzione per cancellare dati esistenti
        if args.clear:
            print("🗑️  Cancellando dati esistenti...")
            cursor = generator.connection.cursor()
            cursor.execute("TRUNCATE leaderboard, users RESTART IDENTITY CASCADE")
            generator.connection.commit()
            cursor.close()
            print("✅ Dati esistenti cancellati")

        # Genera e inserisce dati
        usernames = generator.generate_usernames(args.users)
        generator.insert_users_batch(usernames, args.batch_size)

        scores = generator.generate_scores(args.users, args.distribution)
        generator.insert_leaderboard_batch(scores, args.batch_size)

        # Mostra statistiche finali
        generator.get_current_stats()

        elapsed_time = time.time() - start_time
        print(f"\n⏱️  Tempo totale: {elapsed_time:.2f} secondi")
        print(f"   Performance: {args.users / elapsed_time:.0f} utenti/secondo")

    except KeyboardInterrupt:
        print("\n⚠️  Operazione interrotta dall'utente")
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        sys.exit(1)
    finally:
        generator.disconnect()

    print("\n🎉 Generazione dati completata!")
    print("💡 Ora puoi eseguire i test di performance con performance_test.py")


if __name__ == "__main__":
    main()