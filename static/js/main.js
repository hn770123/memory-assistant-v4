// Memory Assistant v4 - 共通JavaScript

// グローバルユーティリティ関数

/**
 * HTMLエスケープ
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 日時フォーマット
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('ja-JP');
}

/**
 * API呼び出しエラーハンドリング
 */
async function handleApiError(response) {
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `HTTPエラー: ${response.status}`);
    }
    return response;
}

/**
 * 確認ダイアログ
 */
function confirm(message) {
    return window.confirm(message);
}

/**
 * アラート
 */
function alert(message) {
    window.alert(message);
}

// ページ読み込み完了時の処理
document.addEventListener('DOMContentLoaded', () => {
    console.log('Memory Assistant v4 - アプリケーション起動');
});
