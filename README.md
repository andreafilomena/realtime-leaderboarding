# 🎯 PostgreSQL Leaderboard Performance Testing

Progetto per testare e analizzare le performance di una leaderboard in tempo reale con PostgreSQL. Questo sistema ti permette di scoprire **quando e perché** le tradizionali query di leaderboard diventano troppo lente, e quali alternative considerare.

## 🎮 Scenario del Test

Immagina un gioco online dove:
- Migliaia/milioni di giocatori competono
- I punteggi vengono aggiornati continuamente
- I giocatori vogliono vedere la TOP 10 istantaneamente
- Ogni giocatore vuole sapere la sua posizione esatta

**Domande chiave che questo progetto risponde:**
- Con quanti utenti le query diventano inaccettabili?
- Quale operazione è il vero collo di bottiglia?
- Quando serve passare a soluzioni alternative (Redis, denormalizzazione)?

## 📁 Struttura del Progetto

```
├── docker-compose.yml          # PostgreSQL ottimizzato + container Python
├── database/
│   ├── init.sql               # Schema database con indici ottimali
│   └── seed_data.sql          # Dati iniziali per test immediati
├── scripts/
│   ├── populate_data.py       # Generatore dati realistici
│   ├── performance_test.py    # Suite test performance completa
│   └── requirements.txt       # Dipendenze Python
├── results/                   # Output test e analisi
└── README.md                  # Questo file
```

## 🚀 Quick Start

### 1. Avvia l'Ambiente
```bash
# Avvia PostgreSQL con configurazioni ottimizzate
docker-compose up -d

# Verifica che tutto sia attivo
docker-compose ps
```

### 2. Installa Dipendenze Python
```bash
# Entra nella directory scripts
cd scripts

# Installa le librerie necessarie
pip install -r requirements.txt
```

### 3. Genera Dati di Test
```bash
# Test piccolo: 1.000 utenti (rapido)
python populate_data.py --users 1000

# Test medio: 100.000 utenti (realistico)
python populate_data.py --users 100000 --distribution skewed

# Test grande: 1.000.000 utenti (stress test)
python populate_data.py --users 1000000 --distribution skewed --clear
```

### 4. Esegui Test Performance
```bash
# Test rapido
python performance_test.py --iterations 50

# Test completo con salvataggio risultati
python performance_test.py --iterations 200 --save-results

# Test su campione specifico di utenti
python performance_test.py --iterations 100 --users 5000
```

## 📊 Le Tre Operazioni Critiche Testate

### 1. 📝 **UPDATE Punteggio**
```sql
UPDATE leaderboard SET score = score + 100 WHERE user_id = 12345;
```
- **Scenario:** Un giocatore vince una partita
- **Target performance:** < 10ms
- **Critico perché:** Succede continuamente in tempo reale

### 2. 🏆 **SELECT TOP 10**
```sql
SELECT username, score FROM leaderboard
JOIN users ON ... ORDER BY score DESC LIMIT 10;
```
- **Scenario:** Mostrare la classifica
- **Target performance:** < 50ms
- **Critico perché:** È la schermata più vista dai giocatori

### 3. 📍 **Calcolo Posizione Utente** (LA PIÙ PROBLEMATICA!)
```sql
SELECT COUNT(*) + 1 FROM leaderboard WHERE score > (SELECT score FROM leaderboard WHERE user_id = 12345);
```
- **Scenario:** "Sei al 15.847° posto!"
- **Target performance:** < 100ms
- **Critico perché:** Con milioni di utenti può richiedere secondi!

## 🧪 Metodologia di Test Rigorosa

Il progetto implementa best practices per test di performance affidabili:

### ⚡ Precision Timing
- `time.perf_counter()` per precisione al microsecondo
- Eliminazione del "cold start bias" con query di warm-up
- Statistiche complete: media, mediana, percentili, deviazione standard

### 📈 Distribuzione Dati Realistica
```bash
# Distribuzione normale: maggior parte utenti con punteggi medi
--distribution normal

# Distribuzione skewed: pochi pro-player, molti casual (REALISTICA!)
--distribution skewed

# Distribuzione uniforme: tutti i punteggi ugualmente probabili
--distribution uniform
```

### 🔍 Monitoraggio Database Avanzato
- Utilizzo di `pg_stat_statements` per metriche interne PostgreSQL
- Analisi dimensioni tabelle e indici
- Cache hit ratio e I/O patterns

## 📊 Interpretazione Risultati

### ✅ Performance Ottime
- **UPDATE:** < 1ms (eccellente), < 10ms (buono)
- **TOP 10:** < 5ms (eccellente), < 50ms (accettabile)
- **Posizione:** < 100ms (buono), < 1s (accettabile)

### 🚨 Segnali di Allarme
- Posizione utente > 1 secondo → **PROBLEMA SERIO!**
- TOP 10 > 200ms → Indici inefficienti
- UPDATE > 50ms → Contention o lock problems

### 💡 Quando Passare a Soluzioni Alternative

**Scenario 1: E-sport/Gaming Competitivo**
- \> 100K utenti attivi → Redis leaderboard
- Posizione real-time richiesta → Cache con aggiornamenti incrementali

**Scenario 2: App Mobile/Casual Gaming**
- \> 500K utenti → Tabelle denormalizzate con posizioni pre-calcolate
- Aggiornamenti batch notturni accettabili → Materialized views

**Scenario 3: Social Gaming**
- \> 1M utenti → Sharding per regioni/leghe
- Leaderboard locali più globale asincrona

## 🛠️ Comandi di Sviluppo

### Database Management
```bash
# Restart database (preserva dati)
docker-compose restart postgres

# Reset completo database
docker-compose down -v && docker-compose up -d

# Accesso diretto a PostgreSQL
docker-compose exec postgres psql -U testuser -d leaderboard_test
```

### Test Incrementali
```bash
# Test con volumi crescenti per trovare breaking point
python populate_data.py --users 1000 --clear
python performance_test.py --iterations 50

python populate_data.py --users 10000 --clear
python performance_test.py --iterations 50

python populate_data.py --users 100000 --clear
python performance_test.py --iterations 50

# Analizza quando le performance crollano!
```

### Debugging Performance
```bash
# Connetti al database per query manuali
docker-compose exec postgres psql -U testuser -d leaderboard_test

# Query utili per debugging:
# Vedi statistiche indici
SELECT * FROM pg_stat_user_indexes WHERE relname = 'leaderboard';

# Controlla query lente
SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC;

# Dimensioni tabelle
SELECT pg_size_pretty(pg_total_relation_size('leaderboard'));
```

## 🎯 Obiettivi di Apprendimento

Completando questo progetto comprenderai visceralmente:

1. **Perché la scalabilità è difficile** - Vedere una query passare da 1ms a 10 secondi
2. **Importanza degli indici** - Differenza tra scan sequenziale e index scan
3. **Limiti delle soluzioni tradizionali** - Quando PostgreSQL non basta più
4. **Trade-offs architetturali** - Consistenza vs Performance vs Complessità
5. **Metodologie di testing** - Come fare benchmarks affidabili

## 🔮 Esperimenti Avanzati

Una volta padroneggiato il sistema base, prova:

### Test con Concorrenza
```bash
# Simula carichi concorrenti (richiede modifiche agli script)
# Testa cosa succede con 100 UPDATE simultanei
```

### Indici Alternativi
```sql
# Testa indici parziali
CREATE INDEX idx_active_users ON leaderboard (score DESC) WHERE user_id IN (SELECT user_id FROM users WHERE is_active = TRUE);

# Confronta performance con/senza
```

### Partitioning
```sql
# Partiziona per range di punteggi
-- Implementa table partitioning e misura differenze
```

## ⚠️ Note Importanti

- **Dimensione dati:** I test sono significativi solo con dataset realistici (100K+ utenti)
- **Hardware:** I risultati dipendono da CPU, RAM, e storage del sistema
- **PostgreSQL version:** Ottimizzazioni differenti tra versioni
- **Carico sistema:** Esegui test su sistema dedicato per risultati puliti

## 📚 Risorse Aggiuntive

- [PostgreSQL Performance Tips](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Indexing Strategies](https://devcenter.heroku.com/articles/postgresql-indexes)
- [pg_stat_statements Guide](https://www.postgresql.org/docs/current/pgstatstatements.html)

---

## 🎉 Buon Testing!

Questo progetto ti darà una comprensione profonda di come le performance del database si degradano con la scala, e quando è il momento di considerare architetture alternative.

**Non limitarti ai test predefiniti** - sperimenta, modifica, spezza qualcosa e riparala. È così che si impara davvero!