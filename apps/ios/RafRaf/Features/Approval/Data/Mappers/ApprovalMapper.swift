import Foundation

/// Onay DTO <-> Domain model mapper.
enum ApprovalMapper {

    /// ApprovalQuestionDTO -> ApprovalQuestion domain modeline donusturur.
    /// - Parameter dto: WebSocket'ten alinan DTO
    /// - Returns: Domain modeli
    static func toDomain(_ dto: ApprovalQuestionDTO) -> ApprovalQuestion {
        ApprovalQuestion(
            id: dto.approvalId,
            question: dto.question,
            context: dto.context,
            options: dto.options.map { optionToDomain($0) },
            timeoutSeconds: dto.timeoutSeconds,
            category: ApprovalCategory(rawValue: dto.category) ?? .destructive,
            receivedAt: Date()
        )
    }

    /// ApprovalOptionDTO -> ApprovalOption domain modeline donusturur.
    /// - Parameter dto: Secenek DTO
    /// - Returns: Domain modeli
    static func optionToDomain(_ dto: ApprovalOptionDTO) -> ApprovalOption {
        ApprovalOption(
            id: dto.id,
            label: dto.label,
            style: ApprovalOptionStyle(rawValue: dto.style) ?? .secondary
        )
    }

    /// V1.5: ApprovalQuestion domain modelini RFApprovalSheet'in tukettigi
    /// ApprovalSheetRequest'e donusturur.
    ///
    /// Risk siniflandirmasi backend kategorisi -> RFApprovalSheet policy
    /// (design v1-permission-blockers §2.1.3 risk tablosuna uygun;
    /// V1.5 reviewer M1 fix: bridge `low → INFRASTRUCTURE` artik dogru
    /// sekilde `.low` badge'ine map'lendi, daha once yanlislikla `.medium`'a
    /// donusuyordu):
    /// - destructive / deploy -> high risk prompt (user MUST tap; kirmizi)
    /// - writeRemote -> medium risk prompt (sari)
    /// - infrastructure -> low risk prompt (mavi/yesil — Read/Glob/Grep)
    ///
    /// `toolName` ApprovalQuestion.context icindeki "Tool: <name>, Action: ..."
    /// pattern'den parse edilir (build_question_message backend formatina uygun).
    /// Fallback: kategori adi.
    /// - Parameter question: Backend'den gelen onay sorusu
    /// - Returns: Sheet'in tukettigi minimal request
    static func toSheetRequest(question: ApprovalQuestion) -> ApprovalSheetRequest {
        let policy: ApprovalDecisionPolicy = {
            switch question.category {
            case .destructive, .deploy:
                return .prompt(risk: .high)
            case .writeRemote:
                return .prompt(risk: .medium)
            case .infrastructure:
                return .prompt(risk: .low)
            }
        }()

        let toolName = parseToolName(fromContext: question.context)
            ?? defaultToolNameLabel(for: question.category)

        return ApprovalSheetRequest(
            id: question.id,
            toolName: toolName,
            inputPreview: question.question,
            policy: policy,
            timeoutSeconds: question.timeoutSeconds
        )
    }

    /// `toDomain` aliasi (V1.5 task spec talep ediyor — coordinator kontrat
    /// adlandirmasi tutarliligi icin yeni isim).
    /// - Parameter dto: WebSocket'ten alinan DTO
    /// - Returns: Domain modeli
    static func toQuestion(dto: ApprovalQuestionDTO) -> ApprovalQuestion {
        toDomain(dto)
    }

    /// Backend `build_question_message` ciktisi `context = "Tool: Bash, Action: rm -rf"`
    /// formatindadir; bu helper "Bash" kismini cikarir. Ayristirilamazsa nil.
    /// - Parameter contextString: ApprovalQuestion.context
    /// - Returns: Tool ismi veya nil
    static func parseToolName(fromContext contextString: String?) -> String? {
        guard let raw = contextString, !raw.isEmpty else { return nil }
        // "Tool: <name>, Action: ..." -> <name>
        guard raw.lowercased().hasPrefix("tool:") else { return nil }
        let afterPrefix = raw.dropFirst("tool:".count)
        let beforeComma = afterPrefix.split(separator: ",", maxSplits: 1).first ?? Substring()
        let trimmed = beforeComma.trimmingCharacters(in: .whitespaces)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Tool ismi ayristirilamazsa kategori bazli bir generic etiket dondurur.
    private static func defaultToolNameLabel(for category: ApprovalCategory) -> String {
        switch category {
        case .destructive: return "Destructive"
        case .deploy: return "Deploy"
        case .infrastructure: return "Infrastructure"
        case .writeRemote: return "Remote Write"
        }
    }

    /// Domain karar bilgisini ApprovalResponseDTO'ya donusturur.
    /// - Parameters:
    ///   - approvalId: Onay talebi ID'si
    ///   - decision: Kullanici karari
    ///   - note: Kullanici notu
    /// - Returns: WebSocket'e gonderilecek DTO
    static func toResponseDTO(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) -> ApprovalResponseDTO {
        ApprovalResponseDTO(
            approvalId: approvalId,
            decision: decision.rawValue,
            note: note
        )
    }
}
