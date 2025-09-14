-- Dati di esempio iniziali per iniziare subito i test
-- Questi dati vengono inseriti automaticamente dopo la creazione delle tabelle

-- Inserimento di alcuni utenti di esempio per verificare che tutto funzioni
-- Questi sono dati "seed" - piccoli set di dati per test immediati
INSERT INTO users (username, email, registration_date, is_active) VALUES
    ('TestPlayer1', 'player1@test.com', NOW() - INTERVAL '30 days', TRUE),
    ('TestPlayer2', 'player2@test.com', NOW() - INTERVAL '25 days', TRUE),
    ('TestPlayer3', 'player3@test.com', NOW() - INTERVAL '20 days', TRUE),
    ('TestPlayer4', 'player4@test.com', NOW() - INTERVAL '15 days', TRUE),
    ('TestPlayer5', 'player5@test.com', NOW() - INTERVAL '10 days', TRUE),
    ('InactivePlayer', 'inactive@test.com', NOW() - INTERVAL '60 days', FALSE),
    ('TopPlayer', 'top@test.com', NOW() - INTERVAL '5 days', TRUE),
    ('NewPlayer', 'new@test.com', NOW() - INTERVAL '1 day', TRUE);

-- Punteggi iniziali per gli utenti
-- Simuliamo una distribuzione realistica: pochi giocatori con punteggi alti, molti con punteggi bassi
INSERT INTO leaderboard (user_id, score, games_played) VALUES
    (1, 1250, 15),   -- TestPlayer1 - punteggio medio
    (2, 890, 12),    -- TestPlayer2 - punteggio medio-basso
    (3, 2340, 28),   -- TestPlayer3 - punteggio alto
    (4, 567, 8),     -- TestPlayer4 - punteggio basso
    (5, 3450, 45),   -- TestPlayer5 - punteggio molto alto
    (6, 123, 2),     -- InactivePlayer - punteggio molto basso (e utente inattivo)
    (7, 9999, 150),  -- TopPlayer - punteggio altissimo (il campione!)
    (8, 0, 1);       -- NewPlayer - appena iniziato

-- Verifica che i dati siano stati inseriti correttamente
-- Questi commenti mostrano query utili per testare manualmente
--
-- Per vedere tutti gli utenti con i loro punteggi:
-- SELECT u.username, l.score FROM users u JOIN leaderboard l ON u.user_id = l.user_id ORDER BY l.score DESC;
--
-- Per vedere la top 5:
-- SELECT u.username, l.score FROM users u JOIN leaderboard l ON u.user_id = l.user_id ORDER BY l.score DESC LIMIT 5;
--
-- Per vedere la posizione di un utente specifico (TestPlayer3):
-- SELECT username, score, position FROM leaderboard_with_rank WHERE username = 'TestPlayer3';

-- NOTA IMPORTANTE per i test di performance:
-- Questi dati sono TROPPO POCHI per test realistici!
-- Usa lo script populate_data.py per generare migliaia/milioni di record
-- per vedere i veri problemi di performance che emergono con grandi dataset.