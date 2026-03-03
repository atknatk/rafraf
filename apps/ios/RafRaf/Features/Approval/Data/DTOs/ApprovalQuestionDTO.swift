import Foundation

/// Onay sorusu WebSocket mesaj DTO.
/// `shared/api-contracts/ws/approval-messages.json` kontratina uygun.
struct ApprovalQuestionDTO: Codable, Sendable {
    /// Benzersiz onay talebi ID'si.
    let approvalId: String
    /// Kullaniciya gosterilecek soru metni.
    let question: String
    /// Soruya ek bilgi/baglam (opsiyonel).
    let context: String?
    /// Kullanicinin secebilecegi secenek listesi.
    let options: [ApprovalOptionDTO]
    /// Onay bekleme suresi (saniye).
    let timeoutSeconds: Int
    /// Onay kategorisi (deploy, destructive, infrastructure, write_remote).
    let category: String
}

/// Onay secenegi DTO.
struct ApprovalOptionDTO: Codable, Sendable {
    /// Secenek tanimlayicisi (approve, reject, detail).
    let id: String
    /// Kullaniciya gosterilen etiket.
    let label: String
    /// Buton stili (primary, danger, secondary).
    let style: String
}
