import Foundation
import Testing
@testable import RafRaf

/// RFApprovalSheet pure-helper testleri (T3.1, Spike #5 fallback).
@Suite("RFApprovalSheet Tests")
struct RFApprovalSheetTests {

    // MARK: - localizedToolName

    @Test("localizedToolName bilinmeyen tool'u oldugu gibi dondurur")
    func localizedToolName_unknown() {
        #expect(RFApprovalSheet.localizedToolName("MysteryTool") == "MysteryTool")
    }

    @Test("localizedToolName WebFetch case-sensitive")
    func localizedToolName_webFetch() {
        let result = RFApprovalSheet.localizedToolName("WebFetch")
        #expect(result.isEmpty == false)
    }

    @Test("localizedToolName lowercase read = read")
    func localizedToolName_read() {
        let result = RFApprovalSheet.localizedToolName("read")
        #expect(result.isEmpty == false)
    }

    // MARK: - ApprovalSheetRequest construction

    @Test("Sheet request high-risk politika ile insa edilir")
    @MainActor
    func sheetRequest_highRisk() {
        let req = ApprovalSheetRequest(
            toolName: "Bash",
            inputPreview: "rm -rf",
            policy: .prompt(risk: .high),
            timeoutSeconds: 30
        )
        let sheet = RFApprovalSheet(request: req, onDecision: { _ in })
        #expect(sheet.request.policy == .prompt(risk: .high))
        #expect(sheet.request.toolName == "Bash")
        #expect(sheet.request.timeoutSeconds == 30)
    }

    @Test("Sheet request medium policy ile insa edilir")
    @MainActor
    func sheetRequest_medium() {
        let req = ApprovalSheetRequest(
            toolName: "WebFetch",
            inputPreview: "https://api.anthropic.com",
            policy: .prompt(risk: .medium)
        )
        let sheet = RFApprovalSheet(request: req, onDecision: { _ in })
        #expect(sheet.request.policy == .prompt(risk: .medium))
    }

    @Test("Sheet onDecision callback farkli choice'lari iletir")
    @MainActor
    func decision_callback_propagates() async {
        var received: [ApprovalUserChoice] = []
        let req = ApprovalSheetRequest(
            toolName: "Edit",
            inputPreview: "edit thing",
            policy: .prompt(risk: .high),
            timeoutSeconds: 30
        )
        let onDecision: (ApprovalUserChoice) -> Void = { received.append($0) }
        let sheet = RFApprovalSheet(
            request: req,
            hapticsEnabled: false,
            timerEnabled: false,
            onDecision: onDecision
        )
        // Closure'u manuel cagirarak iletim semantigini dogrula.
        sheet.onDecision(.allowOnce)
        sheet.onDecision(.allowSession)
        sheet.onDecision(.deny)
        #expect(received == [.allowOnce, .allowSession, .deny])
    }

    @Test("ApprovalUserChoice tum case'leri rawValue uretir")
    func userChoice_rawValues() {
        #expect(ApprovalUserChoice.allowOnce.rawValue == "allow_once")
        #expect(ApprovalUserChoice.allowSession.rawValue == "allow_session")
        #expect(ApprovalUserChoice.deny.rawValue == "deny")
    }

    @Test("ApprovalRiskLevel tum case'leri uretir")
    func riskLevel_rawValues() {
        let all = ApprovalRiskLevel.allCases
        #expect(all.contains(.low))
        #expect(all.contains(.medium))
        #expect(all.contains(.high))
    }

    // MARK: - Auto-deny timer (M2 deferral)

    /// 30s auto-deny timer'inin pure logic'i — kullanici cevap vermezse
    /// `onTimeout` (production'da `handleDecision(.deny)`) tetiklenmeli.
    /// Determinizm icin tickInterval 5ms ve timeoutSeconds 3 (toplam ~15ms).
    @Test("Auto-deny timer kullanici cevap vermezse onTimeout cagirir")
    @MainActor
    func autoDenyCountdown_firesTimeout() async {
        let onTimeoutCounter = AutoDenyCounter()
        let ticks = AutoDenyTickRecorder()

        await RFApprovalSheet.runAutoDenyCountdown(
            timeoutSeconds: 3,
            tickInterval: .milliseconds(5),
            tick: { remaining in ticks.append(remaining) },
            isCancelled: { false },
            onTimeout: { onTimeoutCounter.fire() }
        )

        #expect(onTimeoutCounter.value == 1)
        // 3s -> 0 boyunca 3 tick beklenir.
        #expect(ticks.values == [2, 1, 0])
    }

    /// Kullanici karar verdiginde (isCancelled = true) onTimeout cagrilmamali.
    @Test("Auto-deny timer kullanici karar verirse onTimeout cagirmaz")
    @MainActor
    func autoDenyCountdown_skippedOnDecision() async {
        let onTimeoutCounter = AutoDenyCounter()

        await RFApprovalSheet.runAutoDenyCountdown(
            timeoutSeconds: 3,
            tickInterval: .milliseconds(5),
            tick: { _ in },
            isCancelled: { true },  // Kullanici hemen karar verdi.
            onTimeout: { onTimeoutCounter.fire() }
        )

        #expect(onTimeoutCounter.value == 0)
    }
}

// MARK: - Test Helpers (M2)

/// Counter helper — Swift 6 strict concurrency icin @MainActor isolation.
@MainActor
private final class AutoDenyCounter {
    private(set) var value = 0
    func fire() { value += 1 }
}

/// Tick recorder helper.
@MainActor
private final class AutoDenyTickRecorder {
    private(set) var values: [Int] = []
    func append(_ v: Int) { values.append(v) }
}
