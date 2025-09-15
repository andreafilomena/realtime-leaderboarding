-- Schema iniziale per il database di test della leaderboard
-- Questo file viene eseguito automaticamente quando PostgreSQL si avvia per la prima volta

-- Abilita l'estensione pg_stat_statements per monitorare le performance delle query
-- MOLTO IMPORTANTE: Questa estensione ci permette di vedere statistiche dettagliate
-- su tutte le query eseguite (tempi, numero di esecuzioni, etc.)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Tabella users: contiene i dati base degli utenti
-- Useremo questa tabella per testare le performance dei JOIN
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,        -- ID univoco dell'utente (generato automaticamente)
    username VARCHAR(50) NOT NULL,     -- Nome utente (massimo 50 caratteri)
    email VARCHAR(100) UNIQUE NOT NULL, -- Email univoca dell'utente
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Data di registrazione
    is_active BOOLEAN DEFAULT TRUE     -- Flag per indicare se l'utente è attivo
);

-- Tabella leaderboard: il cuore del nostro sistema
-- Questa tabella conterrà i punteggi degli utenti che useremo per i test
CREATE TABLE leaderboard (
    user_id INTEGER REFERENCES users(user_id), -- Collegamento alla tabella users
    score BIGINT NOT NULL DEFAULT 0,           -- Punteggio dell'utente (può essere molto grande)
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Ultimo aggiornamento del punteggio
    games_played INTEGER DEFAULT 1,            -- Numero di partite giocate

    -- Chiave primaria: ogni utente può avere una sola riga nella leaderboard
    PRIMARY KEY (user_id)
);

-- INDICI FONDAMENTALI per le performance
-- Senza questi indici, le query sarebbero molto lente con tanti dati

-- Indice sul punteggio in ordine decrescente
-- CRITICO: Questo indice è essenziale per le query "top 10" veloci
-- Senza questo indice, PostgreSQL dovrebbe ordinare TUTTI i record ogni volta
CREATE INDEX idx_leaderboard_score_desc ON leaderboard (score DESC);

-- Indice composto per query che filtrano per utenti attivi con punteggio
-- Utile se vogliamo escludere utenti non attivi dalla leaderboard
-- Nota: Questo indice include tutti i record, il filtro per utenti attivi
-- verrà fatto a livello di query JOIN con la tabella users
CREATE INDEX idx_leaderboard_active_score ON leaderboard (user_id, score DESC);

-- Indice sulla data di ultimo aggiornamento per query temporali
CREATE INDEX idx_leaderboard_last_updated ON leaderboard (last_updated);

-- Funzione per aggiornare automaticamente il timestamp quando un punteggio cambia
-- Questa funzione verrà chiamata automaticamente ogni volta che modifichiamo un record
CREATE OR REPLACE FUNCTION update_last_updated_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger che chiama la funzione di aggiornamento timestamp
-- Ogni volta che facciamo UPDATE sulla tabella leaderboard, il timestamp viene aggiornato automaticamente
CREATE TRIGGER update_leaderboard_timestamp
    BEFORE UPDATE ON leaderboard
    FOR EACH ROW
    EXECUTE FUNCTION update_last_updated_column();

-- Vista per semplificare le query più comuni
-- Questa vista unisce users e leaderboard e calcola la posizione di ogni utente
-- ATTENZIONE: Con molti dati questa vista potrebbe essere lenta!
CREATE VIEW leaderboard_with_rank AS
SELECT
    u.user_id,
    u.username,
    u.email,
    l.score,
    l.games_played,
    l.last_updated,
    -- RANK() calcola la posizione dell'utente nella leaderboard
    -- Gli utenti con lo stesso punteggio avranno la stessa posizione
    RANK() OVER (ORDER BY l.score DESC) as position
FROM users u
JOIN leaderboard l ON u.user_id = l.user_id
WHERE u.is_active = TRUE
ORDER BY l.score DESC;

-- Commenti per il futuro sviluppatore (te stesso tra qualche settimana!):
--
-- PERFORMANCE TIPS:
-- 1. L'indice idx_leaderboard_score_desc è CRITICO per query "TOP N"
-- 2. La query per trovare la posizione di un utente specifico sarà molto lenta
--    con tanti dati - questo è proprio quello che vogliamo testare!
-- 3. La vista leaderboard_with_rank è comoda ma può essere lenta con molti utenti
-- 4. Per sistemi reali con milioni di utenti, considera strategie alternative:
--    - Leaderboard cache (Redis)
--    - Tabelle denormalizzate con posizioni pre-calcolate
--    - Sharding per regione/categoria
--
-- COSA TESTEREMO:
-- - UPDATE performance: quanto tempo per incrementare un punteggio?
-- - SELECT TOP 10: quanto tempo per ottenere i primi 10?
-- - RANK query: quanto tempo per trovare la posizione di un utente specifico?