import Foundation

/// Onay sorusu WebSocket mesaj DTO.
/// `shared/api-contracts/ws/approval-messages.json` kontratina uygun.
///
/// Backend (Pydantic) snake_case JSON gonderiyor; iOS Swift camelCase mapping
/// explicit `CodingKeys` ile yapilir. `WebSocketMessageRouter` decoder
/// `.useDefaultKeys` kullanir (T1.6 sonrasi convention) — strategi degil,
/// kontrat-eslesmesi explicit kontratta tutulur.
struct ApprovalQuestionDTO: Codable, Sendable, Equatable {
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

    enum CodingKeys: String, CodingKey {
        case approvalId = "approval_id"
        case question
        case context
        case options
        case timeoutSeconds = "timeout_seconds"
        case category
    }
}

/// Onay secenegi DTO.
struct ApprovalOptionDTO: Codable, Sendable, Equatable {
    /// Secenek tanimlayicisi (approve, reject, detail).
    let id: String
    /// Kullaniciya gosterilen etiket.
    let label: String
    /// Buton stili (primary, danger, secondary).
    let style: String
}
