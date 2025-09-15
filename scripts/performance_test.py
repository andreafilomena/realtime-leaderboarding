#!/usr/bin/env python3
"""
Script di test delle performance per la leaderboard PostgreSQL.

Questo è il CUORE del progetto: misura precisamente quanto tempo impiegano
le operazioni fondamentali della leaderboard con volumi crescenti di dati.

Tre operazioni critiche testate:
1. UPDATE punteggio utente (simula una partita vinta)
2. SELECT TOP 10 (mostra la classifica)
3. Calcolo posizione utente (la query più problematica!)

Utilizzo:
    python performance_test.py --iterations 100
    python performance_test.py --iterations 50 --users-sample 1000 --save-results
"""

import argparse
import csv
import json
import random
import statistics
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any

import psycopg2
import psycopg2.extras
import numpy as np
from tabulate import tabulate
from tqdm import tqdm


class PerformanceTester:
    """
    Classe principale per testare le performance della leaderboard.

    Implementa metodologie rigorose per misurazioni accurate:
    - Warm-up queries per evitare bias del "cold start"
    - Precision timing con time.perf_counter() (microsecondi)
    - Statistiche complete (media, mediana, percentili, dev.standard)
    - Raccolta metriche PostgreSQL con pg_stat_statements
    """

    def __init__(self, db_config: dict):
        """
        Inizializza il tester con configurazione database.

        Args:
            db_config: Configurazione connessione PostgreSQL
        """
        self.db_config = db_config
        self.connection = None
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'database_stats': {},
            'tests': {}
        }

    def connect(self):
        """Stabilisce connessione al database con configurazioni ottimizzate."""
        try:
            self.connection = psycopg2.connect(
                **self.db_config,
                # Configurazioni per performance testing
                cursor_factory=psycopg2.extras.RealDictCursor  # Risultati come dizionari
            )
            # Disabiliamo autocommit per controllo manuale delle transazioni
            self.connection.autocommit = False
            print(f"✅ Connesso al database per performance testing")

            # Verifica che pg_stat_statements sia attivo
            self._verify_pg_stat_statements()

        except Exception as e:
            print(f"❌ Errore connessione: {e}")
            sys.exit(1)

    def disconnect(self):
        """Chiude la connessione al database."""
        if self.connection:
            self.connection.close()
            print("🔌 Connessione database chiusa")

    def _verify_pg_stat_statements(self):
        """Verifica che pg_stat_statements sia disponibile per le metriche."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM pg_stat_statements LIMIT 1")
            cursor.fetchone()
            print("📊 pg_stat_statements disponibile per metriche avanzate")
        except Exception:
            print("⚠️  pg_stat_statements non disponibile - metriche limitate")
        finally:
            cursor.close()

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Raccoglie statistiche generali del database per contestualizzare i test.

        Returns:
            Dizionario con statistiche del database
        """
        cursor = self.connection.cursor()
        stats = {}

        try:
            # Conta record nelle tabelle
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) FROM leaderboard")
            stats['total_leaderboard_records'] = cursor.fetchone()['count']

            # Statistiche sui punteggi
            cursor.execute("""
                SELECT
                    MIN(score) as min_score,
                    MAX(score) as max_score,
                    AVG(score) as avg_score,
                    STDDEV(score) as stddev_score
                FROM leaderboard
            """)
            score_stats = cursor.fetchone()
            stats.update(dict(score_stats))

            # Dimensione delle tabelle su disco
            cursor.execute("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE tablename IN ('users', 'leaderboard')
            """)
            table_sizes = cursor.fetchall()
            stats['table_sizes'] = {row['tablename']: row['size'] for row in table_sizes}

            # Informazioni sugli indici
            cursor.execute("""
                SELECT
                    indexname,
                    tablename,
                    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
                FROM pg_indexes
                WHERE tablename IN ('users', 'leaderboard')
            """)
            index_info = cursor.fetchall()
            stats['index_sizes'] = {row['indexname']: row['size'] for row in index_info}

        except Exception as e:
            print(f"⚠️  Errore raccolta statistiche database: {e}")

        finally:
            cursor.close()

        return stats

    def warm_up_queries(self, iterations: int = 10):
        """
        Esegue query di "warm-up" per eliminare il bias del cold start.

        MOLTO IMPORTANTE: La prima esecuzione di una query è spesso più lenta
        perché PostgreSQL deve caricare dati in cache. Il warm-up elimina questo bias.

        Args:
            iterations: Numero di query di warm-up da eseguire
        """
        print(f"🔥 Eseguendo {iterations} query di warm-up...")
        cursor = self.connection.cursor()

        warm_up_queries = [
            "SELECT COUNT(*) FROM leaderboard",
            "SELECT * FROM leaderboard ORDER BY score DESC LIMIT 10",
            "SELECT user_id, score FROM leaderboard WHERE user_id = 1",
        ]

        for _ in tqdm(range(iterations), desc="Warm-up"):
            for query in warm_up_queries:
                try:
                    cursor.execute(query)
                    cursor.fetchall()  # Scarica tutti i risultati
                    self.connection.commit()
                except Exception:
                    self.connection.rollback()

        cursor.close()
        print("✅ Warm-up completato")

    def test_score_update_performance(self, iterations: int, user_sample: int = 1000) -> Dict:
        """
        Testa le performance dell'aggiornamento punteggio (operazione #1).

        Simula un utente che vince una partita e incrementa il suo punteggio.
        Questa è un'operazione WRITE che deve essere veloce per un gioco in tempo reale.

        Args:
            iterations: Numero di test da eseguire
            user_sample: Range di utenti da testare (1 to user_sample)

        Returns:
            Dizionario con statistiche dei tempi
        """
        print(f"📝 Test UPDATE performance ({iterations} iterazioni)...")

        cursor = self.connection.cursor()
        times = []

        # Otteniamo il range di user_id validi
        cursor.execute("SELECT MIN(user_id), MAX(user_id) FROM leaderboard")
        result = cursor.fetchone()
        if result is None or result['min'] is None:
            raise ValueError("Database vuoto: nessun record nella tabella leaderboard")

        min_user_id, max_user_id = int(result['min']), int(result['max'])
        # Semplifichiamo: usa sempre il range completo o limitato da user_sample
        max_test_user = min(max_user_id, user_sample)

        # Se user_sample è minore del min_user_id, usa il range completo
        if max_test_user < min_user_id:
            max_test_user = max_user_id

        if min_user_id > max_test_user:
            raise ValueError(f"Range invalido: min_user_id={min_user_id} > max_test_user={max_test_user}")

        for i in tqdm(range(iterations), desc="Test UPDATE"):
            # Scegliamo un utente casuale da testare
            user_id = random.randint(min_user_id, max_test_user)
            score_increment = random.randint(10, 500)  # Incremento realistico

            # MISURAZIONE PRECISA: time.perf_counter() ha precisione di microsecondi
            start_time = time.perf_counter()

            try:
                cursor.execute("""
                    UPDATE leaderboard
                    SET score = score + %s,
                        games_played = games_played + 1
                    WHERE user_id = %s
                """, (score_increment, user_id))

                # Commit immediato per simulare operazione completa
                self.connection.commit()

                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000  # Converti in millisecondi
                times.append(execution_time)

            except Exception as e:
                self.connection.rollback()
                print(f"❌ Errore UPDATE per user {user_id}: {e}")

        cursor.close()

        # Calcola statistiche complete
        stats = self._calculate_statistics(times, "UPDATE Score")
        return stats

    def test_top_leaderboard_performance(self, iterations: int, limit: int = 10) -> Dict:
        """
        Testa le performance del recupero TOP N (operazione #2).

        Questa è la query che tutti i giocatori vedono: la classifica dei migliori.
        Deve essere velocissima anche con milioni di utenti!

        Args:
            iterations: Numero di test da eseguire
            limit: Numero di top players da recuperare (default: 10)

        Returns:
            Dizionario con statistiche dei tempi
        """
        print(f"🏆 Test SELECT TOP {limit} performance ({iterations} iterazioni)...")

        cursor = self.connection.cursor()
        times = []

        for i in tqdm(range(iterations), desc=f"Test TOP {limit}"):
            start_time = time.perf_counter()

            try:
                cursor.execute("""
                    SELECT u.username, l.score, l.games_played
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.user_id
                    WHERE u.is_active = TRUE
                    ORDER BY l.score DESC
                    LIMIT %s
                """, (limit,))

                # Fetch dei risultati per simulare utilizzo reale
                results = cursor.fetchall()
                self.connection.commit()

                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000  # millisecondi
                times.append(execution_time)

                # Verifichiamo che abbiamo ottenuto risultati
                if i == 0:  # Solo per il primo test
                    print(f"   Top {limit} query restituisce {len(results)} risultati")

            except Exception as e:
                self.connection.rollback()
                print(f"❌ Errore SELECT TOP: {e}")

        cursor.close()

        stats = self._calculate_statistics(times, f"SELECT TOP {limit}")
        return stats

    def test_user_ranking_performance(self, iterations: int, user_sample: int = 1000) -> Dict:
        """
        Testa le performance del calcolo posizione utente (operazione #3).

        QUESTA È LA QUERY PIÙ PROBLEMATICA! Per trovare la posizione di un utente
        specifico, PostgreSQL deve potenzialmente contare tutti gli utenti con
        punteggi superiori. Con milioni di utenti, diventa MOLTO lenta!

        Args:
            iterations: Numero di test da eseguire
            user_sample: Range di utenti da testare

        Returns:
            Dizionario con statistiche dei tempi
        """
        print(f"📍 Test calcolo posizione utente ({iterations} iterazioni)...")

        cursor = self.connection.cursor()
        times = []

        # Otteniamo utenti validi
        cursor.execute("SELECT MIN(user_id), MAX(user_id) FROM leaderboard")
        result = cursor.fetchone()
        if result is None or result['min'] is None:
            raise ValueError("Database vuoto: nessun record nella tabella leaderboard")

        min_user_id, max_user_id = int(result['min']), int(result['max'])
        # Semplifichiamo: usa sempre il range completo o limitato da user_sample
        max_test_user = min(max_user_id, user_sample)

        # Se user_sample è minore del min_user_id, usa il range completo
        if max_test_user < min_user_id:
            max_test_user = max_user_id

        if min_user_id > max_test_user:
            raise ValueError(f"Range invalido: min_user_id={min_user_id} > max_test_user={max_test_user}")

        for i in tqdm(range(iterations), desc="Test posizione utente"):
            # Scegliamo un utente casuale
            user_id = random.randint(min_user_id, max_test_user)

            start_time = time.perf_counter()

            try:
                # Metodo 1: Query con COUNT (spesso lenta con molti dati)
                cursor.execute("""
                    SELECT
                        u.username,
                        l.score,
                        (SELECT COUNT(*) + 1
                         FROM leaderboard l2
                         JOIN users u2 ON l2.user_id = u2.user_id
                         WHERE u2.is_active = TRUE AND l2.score > l.score) as position
                    FROM leaderboard l
                    JOIN users u ON l.user_id = u.user_id
                    WHERE l.user_id = %s AND u.is_active = TRUE
                """, (user_id,))

                result = cursor.fetchone()
                self.connection.commit()

                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000
                times.append(execution_time)

                # Log del risultato solo per il primo test
                if i == 0 and result:
                    print(f"   Utente {result['username']}: posizione {result['position']}, punteggio {result['score']}")

            except Exception as e:
                self.connection.rollback()
                print(f"❌ Errore calcolo posizione per user {user_id}: {e}")

        cursor.close()

        stats = self._calculate_statistics(times, "Calcolo Posizione Utente")
        return stats

    def test_user_ranking_with_window_function(self, iterations: int, user_sample: int = 1000) -> Dict:
        """
        Testa un approccio alternativo per il calcolo della posizione usando WINDOW functions.

        Questo metodo può essere più efficiente del COUNT, ma richiede più memoria.
        È importante testare entrambi gli approcci per confrontare le performance.

        Args:
            iterations: Numero di test da eseguire
            user_sample: Range di utenti da testare

        Returns:
            Dizionario con statistiche dei tempi
        """
        print(f"🪟 Test posizione con WINDOW function ({iterations} iterazioni)...")

        cursor = self.connection.cursor()
        times = []

        cursor.execute("SELECT MIN(user_id), MAX(user_id) FROM leaderboard")
        result = cursor.fetchone()
        if result is None or result['min'] is None:
            raise ValueError("Database vuoto: nessun record nella tabella leaderboard")

        min_user_id, max_user_id = int(result['min']), int(result['max'])
        # Semplifichiamo: usa sempre il range completo o limitato da user_sample
        max_test_user = min(max_user_id, user_sample)

        # Se user_sample è minore del min_user_id, usa il range completo
        if max_test_user < min_user_id:
            max_test_user = max_user_id

        if min_user_id > max_test_user:
            raise ValueError(f"Range invalido: min_user_id={min_user_id} > max_test_user={max_test_user}")

        for i in tqdm(range(iterations), desc="Test WINDOW function"):
            user_id = random.randint(min_user_id, max_test_user)

            start_time = time.perf_counter()

            try:
                # Metodo 2: Window function (può essere più efficiente)
                cursor.execute("""
                    WITH ranked_users AS (
                        SELECT
                            l.user_id,
                            u.username,
                            l.score,
                            RANK() OVER (ORDER BY l.score DESC) as position
                        FROM leaderboard l
                        JOIN users u ON l.user_id = u.user_id
                        WHERE u.is_active = TRUE
                    )
                    SELECT username, score, position
                    FROM ranked_users
                    WHERE user_id = %s
                """, (user_id,))

                result = cursor.fetchone()
                self.connection.commit()

                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000
                times.append(execution_time)

            except Exception as e:
                self.connection.rollback()
                print(f"❌ Errore WINDOW function per user {user_id}: {e}")

        cursor.close()

        stats = self._calculate_statistics(times, "Posizione con WINDOW Function")
        return stats

    def _calculate_statistics(self, times: List[float], operation_name: str) -> Dict:
        """
        Calcola statistiche complete sui tempi di esecuzione.

        Queste statistiche sono FONDAMENTALI per capire le performance reali:
        - Media: tempo tipico
        - Mediana: tempo "centrale" (meno influenzata da outliers)
        - Percentili: per capire la distribuzione
        - Deviazione standard: quanto variano i tempi

        Args:
            times: Lista dei tempi in millisecondi
            operation_name: Nome dell'operazione per logging

        Returns:
            Dizionario con tutte le statistiche
        """
        if not times:
            return {'error': 'Nessun dato disponibile'}

        stats = {
            'operation': operation_name,
            'sample_size': len(times),
            'min_ms': min(times),
            'max_ms': max(times),
            'mean_ms': statistics.mean(times),
            'median_ms': statistics.median(times),
            'stdev_ms': statistics.stdev(times) if len(times) > 1 else 0,
            'p95_ms': np.percentile(times, 95),  # 95% dei test sono più veloci di questo
            'p99_ms': np.percentile(times, 99),  # 99% dei test sono più veloci di questo
        }

        # Calcola performance in operazioni/secondo
        if stats['mean_ms'] > 0:
            stats['ops_per_second'] = 1000 / stats['mean_ms']
        else:
            stats['ops_per_second'] = float('inf')

        return stats

    def get_pg_stat_statements_info(self) -> Dict:
        """
        Raccoglie statistiche avanzate da pg_stat_statements.

        Queste metriche mostrano cosa succede "dentro" PostgreSQL:
        - Quante volte ogni query è stata eseguita
        - Tempo totale e medio per tipo di query
        - Cache hits vs disk reads
        - Ottimizzazioni applicate

        Returns:
            Dizionario con statistiche pg_stat_statements
        """
        cursor = self.connection.cursor()
        pg_stats = {}

        try:
            # Query più frequenti
            cursor.execute("""
                SELECT
                    SUBSTRING(query, 1, 100) as query_snippet,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    rows
                FROM pg_stat_statements
                ORDER BY calls DESC
                LIMIT 10
            """)
            most_frequent = cursor.fetchall()
            pg_stats['most_frequent_queries'] = [dict(row) for row in most_frequent]

            # Query più lente
            cursor.execute("""
                SELECT
                    SUBSTRING(query, 1, 100) as query_snippet,
                    calls,
                    total_exec_time,
                    mean_exec_time
                FROM pg_stat_statements
                WHERE calls > 1
                ORDER BY mean_exec_time DESC
                LIMIT 10
            """)
            slowest = cursor.fetchall()
            pg_stats['slowest_queries'] = [dict(row) for row in slowest]

            # Statistiche generali
            cursor.execute("""
                SELECT
                    SUM(calls) as total_calls,
                    SUM(total_exec_time) as total_time,
                    AVG(mean_exec_time) as avg_time
                FROM pg_stat_statements
            """)
            general = cursor.fetchone()
            pg_stats['general_stats'] = dict(general) if general else {}

        except Exception as e:
            print(f"⚠️  Impossibile raccogliere pg_stat_statements: {e}")
            pg_stats['error'] = str(e)

        finally:
            cursor.close()

        return pg_stats

    def run_complete_test_suite(self, iterations: int, user_sample: int = 1000) -> Dict:
        """
        Esegue la suite completa di test delle performance.

        Questa è la funzione "main" che orchestra tutti i test in sequenza,
        raccoglie tutte le metriche e produce un report completo.

        Args:
            iterations: Numero di iterazioni per ogni test
            user_sample: Range di utenti da utilizzare nei test

        Returns:
            Dizionario con tutti i risultati
        """
        print("\n🚀 AVVIO SUITE COMPLETA TEST PERFORMANCE")
        print("=" * 60)

        start_time = time.time()

        # Raccoglie informazioni iniziali sul database
        print("📊 Raccogliendo statistiche database...")
        self.results['database_stats'] = self.get_database_stats()

        # Warm-up essenziale
        self.warm_up_queries()

        # Reset statistiche pg_stat_statements per test puliti
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT pg_stat_statements_reset()")
            self.connection.commit()
            cursor.close()
            print("🧹 Statistiche pg_stat_statements resetted")
        except Exception:
            print("⚠️  Non è possibile resettare pg_stat_statements")

        # ESECUZIONE DEI TEST PRINCIPALI
        print("\n" + "=" * 60)

        # Test 1: Aggiornamento punteggi
        self.results['tests']['score_update'] = self.test_score_update_performance(
            iterations, user_sample
        )

        # Test 2: Top leaderboard
        self.results['tests']['top_leaderboard'] = self.test_top_leaderboard_performance(
            iterations
        )

        # Test 3: Posizione utente (metodo classico)
        self.results['tests']['user_ranking'] = self.test_user_ranking_performance(
            iterations, user_sample
        )

        # Test 4: Posizione utente (window function)
        self.results['tests']['user_ranking_window'] = self.test_user_ranking_with_window_function(
            iterations, user_sample
        )

        # Raccoglie statistiche finali
        print("\n📈 Raccogliendo metriche finali PostgreSQL...")
        self.results['pg_stat_statements'] = self.get_pg_stat_statements_info()

        total_time = time.time() - start_time
        self.results['total_test_time'] = total_time

        print(f"\n✅ Suite test completata in {total_time:.2f} secondi")
        return self.results

    def save_text_summary(self, output_dir: str = "/app/results", filename: str = None):
        """
        Salva il riassunto testuale dei risultati in un file .txt.

        Args:
            output_dir: Directory di output
            filename: Nome del file (se None, genera nome con timestamp)
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/performance_summary_{timestamp}.txt"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("📊 RIASSUNTO RISULTATI PERFORMANCE TEST\n")
                f.write("=" * 80 + "\n\n")

                # Database info
                f.write("🗄️  DATABASE:\n")
                if 'database_stats' in self.results:
                    stats = self.results['database_stats']
                    total_users = stats.get('total_users', 'N/A')
                    leaderboard_records = stats.get('leaderboard_records', 'N/A')
                    avg_score = stats.get('avg_score', 'N/A')

                    # Formatta con virgole solo se è un numero
                    total_users_str = f"{total_users:,}" if isinstance(total_users, int) else total_users
                    leaderboard_records_str = f"{leaderboard_records:,}" if isinstance(leaderboard_records, int) else leaderboard_records

                    f.write(f"   Utenti totali: {total_users_str}\n")
                    f.write(f"   Record leaderboard: {leaderboard_records_str}\n")
                    f.write(f"   Punteggio medio: {avg_score}\n")
                f.write("\n")

                # Performance summary table
                f.write("🎯 PERFORMANCE SUMMARY:\n")

                # Create table data
                table_data = []
                tests = self.results.get('tests', {})

                if 'score_update' in tests:
                    data = tests['score_update']
                    table_data.append([
                        "UPDATE Score",
                        f"{data['mean_ms']:.2f}",
                        f"{data['median_ms']:.2f}",
                        f"{data['p95_ms']:.2f}",
                        f"{data['ops_per_second']:.1f}",
                        f"{data['sample_size']}"
                    ])

                if 'top_leaderboard' in tests:
                    data = tests['top_leaderboard']
                    table_data.append([
                        "SELECT TOP 10",
                        f"{data['mean_ms']:.2f}",
                        f"{data['median_ms']:.2f}",
                        f"{data['p95_ms']:.2f}",
                        f"{data['ops_per_second']:.1f}",
                        f"{data['sample_size']}"
                    ])

                if 'user_ranking' in tests:
                    data = tests['user_ranking']
                    table_data.append([
                        "Calcolo Posizione Utente",
                        f"{data['mean_ms']:.2f}",
                        f"{data['median_ms']:.2f}",
                        f"{data['p95_ms']:.2f}",
                        f"{data['ops_per_second']:.1f}",
                        f"{data['sample_size']}"
                    ])

                if 'user_ranking_window' in tests:
                    data = tests['user_ranking_window']
                    table_data.append([
                        "Posizione con WINDOW Function",
                        f"{data['mean_ms']:.2f}",
                        f"{data['median_ms']:.2f}",
                        f"{data['p95_ms']:.2f}",
                        f"{data['ops_per_second']:.1f}",
                        f"{data['sample_size']}"
                    ])

                # Write table using tabulate
                headers = ["Operazione", "Media (ms)", "Mediana (ms)", "P95 (ms)", "Ops/sec", "Campioni"]
                table_str = tabulate(table_data, headers=headers, tablefmt="grid")
                f.write(table_str + "\n\n")

                # Analysis
                f.write("🔍 ANALISI PERFORMANCE:\n")
                if 'score_update' in tests:
                    update_time = tests['score_update']['mean_ms']
                    if update_time < 10:
                        f.write("   👍 UPDATE: Performance accettabili (<10ms)\n")
                    else:
                        f.write("   ⚠️  UPDATE: Performance da ottimizzare (>10ms)\n")

                if 'top_leaderboard' in tests:
                    select_time = tests['top_leaderboard']['mean_ms']
                    if select_time < 5:
                        f.write("   ✅ TOP 10: Ottime performance (<5ms)\n")
                    else:
                        f.write("   ⚠️  TOP 10: Performance da ottimizzare (>5ms)\n")

                f.write("\n🎯 POSIZIONE UTENTE (query più critica):\n")
                if 'user_ranking' in tests and 'user_ranking_window' in tests:
                    rank_time = tests['user_ranking']['mean_ms']
                    window_time = tests['user_ranking_window']['mean_ms']
                    f.write(f"   Metodo COUNT: {rank_time:.2f}ms\n")
                    f.write(f"   Metodo WINDOW: {window_time:.2f}ms\n")

                    if window_time < rank_time:
                        improvement = ((rank_time - window_time) / rank_time) * 100
                        f.write(f"   💡 Window function è {improvement:.1f}% più veloce del COUNT\n")

                f.write(f"\n📅 Test eseguito: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("💡 Analizza i risultati per ottimizzare il database o considerare architetture alternative\n")

            print(f"📄 Riassunto testuale salvato in: {filename}")
        except Exception as e:
            print(f"❌ Errore salvataggio riassunto: {e}")

    def print_results_summary(self):
        """Stampa un riassunto formattato dei risultati."""
        print("\n" + "=" * 80)
        print("📊 RIASSUNTO RISULTATI PERFORMANCE TEST")
        print("=" * 80)

        # Informazioni sul database
        db_stats = self.results.get('database_stats', {})
        print(f"\n🗄️  DATABASE:")
        print(f"   Utenti totali: {db_stats.get('total_users', 'N/A'):,}")
        print(f"   Record leaderboard: {db_stats.get('total_leaderboard_records', 'N/A'):,}")
        print(f"   Punteggio medio: {db_stats.get('avg_score', 0):.1f}")

        # Risultati dei test in formato tabellare
        test_results = []
        for test_name, stats in self.results.get('tests', {}).items():
            if 'error' not in stats:
                test_results.append([
                    stats.get('operation', test_name),
                    f"{stats.get('mean_ms', 0):.2f}",
                    f"{stats.get('median_ms', 0):.2f}",
                    f"{stats.get('p95_ms', 0):.2f}",
                    f"{stats.get('ops_per_second', 0):.1f}",
                    stats.get('sample_size', 0)
                ])

        if test_results:
            headers = ["Operazione", "Media (ms)", "Mediana (ms)", "P95 (ms)", "Ops/sec", "Campioni"]
            print(f"\n🎯 PERFORMANCE SUMMARY:")
            print(tabulate(test_results, headers=headers, tablefmt="grid"))

        # Analisi e raccomandazioni
        self._print_performance_analysis()

    def _print_performance_analysis(self):
        """Stampa analisi e raccomandazioni basate sui risultati."""
        print(f"\n🔍 ANALISI PERFORMANCE:")

        tests = self.results.get('tests', {})

        # Analizza UPDATE performance
        update_stats = tests.get('score_update', {})
        if update_stats.get('mean_ms', 0) < 1:
            print("   ✅ UPDATE: Ottime performance (<1ms)")
        elif update_stats.get('mean_ms', 0) < 10:
            print("   👍 UPDATE: Performance accettabili (<10ms)")
        else:
            print("   ⚠️  UPDATE: Performance sotto soglia ottimale (>10ms)")

        # Analizza TOP query
        top_stats = tests.get('top_leaderboard', {})
        if top_stats.get('mean_ms', 0) < 5:
            print("   ✅ TOP 10: Ottime performance (<5ms)")
        elif top_stats.get('mean_ms', 0) < 50:
            print("   👍 TOP 10: Performance accettabili (<50ms)")
        else:
            print("   ⚠️  TOP 10: Performance sotto soglia (>50ms)")

        # Analizza query posizione (la più problematica)
        rank_stats = tests.get('user_ranking', {})
        rank_window_stats = tests.get('user_ranking_window', {})

        rank_time = rank_stats.get('mean_ms', 0)
        window_time = rank_window_stats.get('mean_ms', 0)

        print(f"\n🎯 POSIZIONE UTENTE (query più critica):")
        print(f"   Metodo COUNT: {rank_time:.2f}ms")
        print(f"   Metodo WINDOW: {window_time:.2f}ms")

        if rank_time > 1000:  # > 1 secondo
            print("   🚨 ATTENZIONE: Query posizione troppo lenta per uso real-time!")
            print("      Raccomandazioni:")
            print("      - Considera cache Redis per posizioni")
            print("      - Implementa tabella denormalizzata con posizioni pre-calcolate")
            print("      - Valuta sharding per regioni/categorie")

        if window_time < rank_time:
            improvement = ((rank_time - window_time) / rank_time) * 100
            print(f"   💡 Window function è {improvement:.1f}% più veloce del COUNT")

    def save_results_to_file(self, output_dir: str = "/app/results", filename: str = None):
        """
        Salva i risultati dettagliati in un file JSON.

        Args:
            filename: Nome del file (se None, genera nome con timestamp)
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/performance_results_{timestamp}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
            print(f"💾 Risultati salvati in: {filename}")
        except Exception as e:
            print(f"❌ Errore salvataggio file: {e}")

    def save_results_to_csv(self, output_dir: str = "/app/results", filename: str = None):
        """
        Salva un riassunto dei risultati in formato CSV per analisi Excel.

        Args:
            filename: Nome del file CSV
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/performance_summary_{timestamp}.csv"

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'Timestamp', 'Operation', 'Mean_ms', 'Median_ms', 'Min_ms', 'Max_ms',
                    'P95_ms', 'P99_ms', 'Stdev_ms', 'Ops_per_second', 'Sample_size'
                ])

                # Dati dei test
                timestamp = self.results.get('timestamp', '')
                for test_name, stats in self.results.get('tests', {}).items():
                    if 'error' not in stats:
                        writer.writerow([
                            timestamp,
                            stats.get('operation', test_name),
                            stats.get('mean_ms', 0),
                            stats.get('median_ms', 0),
                            stats.get('min_ms', 0),
                            stats.get('max_ms', 0),
                            stats.get('p95_ms', 0),
                            stats.get('p99_ms', 0),
                            stats.get('stdev_ms', 0),
                            stats.get('ops_per_second', 0),
                            stats.get('sample_size', 0)
                        ])

            print(f"📊 Riassunto CSV salvato in: {filename}")
        except Exception as e:
            print(f"❌ Errore salvataggio CSV: {e}")


def main():
    """Funzione principale con gestione argomenti da riga di comando."""
    parser = argparse.ArgumentParser(
        description="Test performance leaderboard PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  python performance_test.py --iterations 50                    # Test rapido
  python performance_test.py --iterations 200 --save-results    # Test completo con salvataggio
  python performance_test.py --iterations 100 --users 5000      # Test con campione specifico
        """
    )

    parser.add_argument(
        '--iterations', '-i',
        type=int,
        default=50,
        help='Numero di iterazioni per ogni test (default: 50)'
    )

    parser.add_argument(
        '--users-sample', '--users',
        type=int,
        default=1000,
        help='Range di utenti da testare (1 to N, default: 1000)'
    )

    parser.add_argument(
        '--save-results',
        action='store_true',
        help='Salva risultati dettagliati in file JSON e CSV'
    )

    parser.add_argument(
        '--output-dir',
        default='/app/results',
        help='Directory per salvare i risultati (default: /app/results)'
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

    print("🎯 PERFORMANCE TESTER LEADERBOARD POSTGRESQL")
    print(f"   Iterazioni per test: {args.iterations}")
    print(f"   Campione utenti: 1-{args.users_sample}")
    print(f"   Salvataggio risultati: {'SÌ' if args.save_results else 'NO'}")

    # Inizializza e esegui test
    tester = PerformanceTester(db_config)

    try:
        tester.connect()

        # Esegue la suite completa
        results = tester.run_complete_test_suite(args.iterations, args.users_sample)

        # Mostra risultati
        tester.print_results_summary()

        # Salva risultati se richiesto
        if args.save_results:
            tester.save_results_to_file(args.output_dir)
            tester.save_results_to_csv(args.output_dir)
            tester.save_text_summary(args.output_dir)

    except KeyboardInterrupt:
        print("\n⚠️  Test interrotti dall'utente")
    except Exception as e:
        print(f"\n❌ Errore durante i test: {e}")
        sys.exit(1)
    finally:
        tester.disconnect()

    print("\n🎉 Performance testing completato!")
    print("💡 Analizza i risultati per ottimizzare il database o considerare architetture alternative")


if __name__ == "__main__":
    main()