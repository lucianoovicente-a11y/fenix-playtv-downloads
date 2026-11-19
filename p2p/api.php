<?php
// Fênix P2P - API de usuários/códigos (admin + validação do site)
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Headers: Content-Type, X-Admin-Token');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { exit; }

$ADMIN_HASH = '8887f55737e775b07856be38d0de1f167f5498515adc162b45395c9b605a516c'; // sha256 da senha do admin
$DATA = __DIR__ . '/data/usuarios.json';

function carregar($f) {
    $j = file_exists($f) ? json_decode(file_get_contents($f), true) : [];
    if (!is_array($j)) $j = [];
    if (!isset($j['usuarios']) || !is_array($j['usuarios'])) $j['usuarios'] = [];
    return $j;
}
function salvar($f, $d) {
    if (!is_dir(dirname($f))) mkdir(dirname($f), 0755, true);
    if (empty($d['usuarios'])) $d['usuarios'] = new stdClass();
    file_put_contents($f, json_encode($d, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT), LOCK_EX);
}
function resp($a) { echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }
function entrada() {
    $raw = file_get_contents('php://input');
    $j = json_decode($raw, true);
    return is_array($j) ? $j : $_REQUEST;
}
function tokenOk($hash) {
    $h = $_SERVER['HTTP_X_ADMIN_TOKEN'] ?? '';
    return hash_equals($hash, $h);
}

$in = entrada();
$acao = $in['acao'] ?? '';

switch ($acao) {
    case 'ping':
        resp(['ok' => true]);

    case 'login':
        $s = $in['senha'] ?? '';
        if (hash_equals($ADMIN_HASH, hash('sha256', $s))) resp(['ok' => true, 'token' => $ADMIN_HASH]);
        resp(['ok' => false, 'erro' => 'Senha incorreta.']);

    case 'validar': // usado pelo site: código existe e está ativo?
        $cod = trim($in['codigo'] ?? '');
        $d = carregar($DATA);
        $u = $d['usuarios'][$cod] ?? null;
        if ($u && empty($u['bloqueado'])) resp(['ok' => true, 'nome' => $u['nome'] ?? '']);
        resp(['ok' => false]);

    case 'listar':
        if (!tokenOk($ADMIN_HASH)) resp(['ok' => false, 'erro' => 'Sem permissão.']);
        $d = carregar($DATA);
        resp(['ok' => true, 'usuarios' => $d['usuarios']]);

    case 'criar': // admin (token) ou painel StreamFlow/Gestor (token do painel)
        $PANEL_TOKEN = 'fenix-p2p-painel-7f3a9c21';
        $tok = $_SERVER['HTTP_X_ADMIN_TOKEN'] ?? '';
        if (!hash_equals($ADMIN_HASH, $tok) && !hash_equals($PANEL_TOKEN, $tok)) resp(['ok' => false, 'erro' => 'Sem permissão.']);
        $nome = trim($in['nome'] ?? '');
        if ($nome === '') resp(['ok' => false, 'erro' => 'Digite o nome.']);
        $d = carregar($DATA);
        do { $cod = strval(random_int(1000, 9999)); } while (isset($d['usuarios'][$cod]));
        $d['usuarios'][$cod] = ['nome' => $nome, 'criado' => date('Y-m-d H:i'), 'bloqueado' => false];
        salvar($DATA, $d);
        resp(['ok' => true, 'codigo' => $cod, 'nome' => $nome]);

    case 'bloquear':
    case 'desbloquear':
        if (!tokenOk($ADMIN_HASH)) resp(['ok' => false, 'erro' => 'Sem permissão.']);
        $cod = trim($in['codigo'] ?? '');
        $d = carregar($DATA);
        if (!isset($d['usuarios'][$cod])) resp(['ok' => false, 'erro' => 'Código não encontrado.']);
        $d['usuarios'][$cod]['bloqueado'] = ($acao === 'bloquear');
        salvar($DATA, $d);
        resp(['ok' => true]);

    case 'excluir':
        if (!tokenOk($ADMIN_HASH)) resp(['ok' => false, 'erro' => 'Sem permissão.']);
        $cod = trim($in['codigo'] ?? '');
        $d = carregar($DATA);
        unset($d['usuarios'][$cod]);
        salvar($DATA, $d);
        resp(['ok' => true]);

    default:
        resp(['ok' => false, 'erro' => 'Ação inválida.']);
}
