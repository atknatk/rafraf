import Foundation
import Testing
@testable import RafRaf

/// ApprovalToolPolicy testleri (T3.1, Spike #5 fallback agaci).
///
/// Politika:
///   - read/grep/ls/glob/cat/pwd → autoAllow
///   - write/edit/multiedit/patch → prompt(high)
///   - bash + safe (ls/pwd/cat/which/echo) → autoAllow
///   - bash + diger → prompt(high)
///   - WebFetch/WebSearch → prompt(medium)
///   - Tanimsiz → prompt(medium)
@Suite("ApprovalToolPolicy Tests")
struct ApprovalToolPolicyTests {

    // MARK: - Read-only auto-allow

    @Test("read/grep/ls/glob/cat/pwd auto-allow")
    func readOnly_autoAllow() {
        for tool in ["read", "Read", "grep", "GREP", "ls", "glob", "cat", "pwd"] {
            let decision = ApprovalToolPolicy.decide(toolName: tool)
            #expect(decision == .autoAllow, "Tool \(tool) auto-allow olmali")
        }
    }

    // MARK: - Write-class prompt (high)

    @Test("write/edit/multiedit/patch high-risk prompt")
    func writeClass_promptHigh() {
        for tool in ["write", "Write", "edit", "Edit", "multiedit", "patch"] {
            let decision = ApprovalToolPolicy.decide(toolName: tool)
            #expect(decision == .prompt(risk: .high), "Tool \(tool) high prompt olmali")
        }
    }

    // MARK: - Bash

    @Test("Bash + ls/pwd/cat safe komutlari auto-allow")
    func bash_safeCommands_autoAllow() {
        for cmd in ["ls -la", "pwd", "cat README.md", "which python", "echo hello"] {
            let decision = ApprovalToolPolicy.decide(toolName: "bash", command: cmd)
            #expect(decision == .autoAllow, "Bash '\(cmd)' auto-allow olmali")
        }
    }

    @Test("Bash unsafe komut high-risk prompt")
    func bash_unsafe_promptHigh() {
        for cmd in ["rm -rf /tmp", "git push --force", "curl https://evil", "sudo apt-get install"] {
            let decision = ApprovalToolPolicy.decide(toolName: "bash", command: cmd)
            #expect(decision == .prompt(risk: .high), "Bash '\(cmd)' high prompt olmali")
        }
    }

    @Test("Bash komut yoksa high prompt (guvenlik default)")
    func bash_noCommand_promptHigh() {
        let decision = ApprovalToolPolicy.decide(toolName: "bash", command: nil)
        #expect(decision == .prompt(risk: .high))
    }

    @Test("Bash bos string komut high prompt")
    func bash_emptyCommand_promptHigh() {
        let decision = ApprovalToolPolicy.decide(toolName: "Bash", command: "")
        #expect(decision == .prompt(risk: .high))
    }

    // MARK: - Network tools

    @Test("WebFetch ve WebSearch medium prompt")
    func networkTools_promptMedium() {
        #expect(ApprovalToolPolicy.decide(toolName: "WebFetch") == .prompt(risk: .medium))
        #expect(ApprovalToolPolicy.decide(toolName: "WebSearch") == .prompt(risk: .medium))
    }

    @Test("WebFetch case-sensitive (lowercase eslesmiyor)")
    func networkTools_caseSensitive() {
        // lowercase 'webfetch' tanimsiz tool olarak medium prompt'a duser
        let decision = ApprovalToolPolicy.decide(toolName: "webfetch")
        #expect(decision == .prompt(risk: .medium))
    }

    // MARK: - Unknown tool default

    @Test("Tanimsiz tool default medium prompt")
    func unknown_defaultMedium() {
        let decision = ApprovalToolPolicy.decide(toolName: "MysteryTool")
        #expect(decision == .prompt(risk: .medium))
    }

    // MARK: - Whitespace handling

    @Test("Tool ismi etrafindaki bosluklar trim edilir")
    func whitespace_trimmed() {
        let decision = ApprovalToolPolicy.decide(toolName: "  read  ")
        #expect(decision == .autoAllow)
    }

    // MARK: - firstToken

    @Test("firstToken ilk kelimeyi dondurur, bos string nil")
    func firstToken_basics() {
        #expect(ApprovalToolPolicy.firstToken(of: "ls -la") == "ls")
        #expect(ApprovalToolPolicy.firstToken(of: "  pwd") == "pwd")
        #expect(ApprovalToolPolicy.firstToken(of: "rm -rf /") == "rm")
        #expect(ApprovalToolPolicy.firstToken(of: "") == nil)
        #expect(ApprovalToolPolicy.firstToken(of: "   ") == nil)
        #expect(ApprovalToolPolicy.firstToken(of: "single") == "single")
    }

    // MARK: - sessionAllowKey

    @Test("sessionAllowKey tool + komut bilesimi")
    func sessionAllowKey_combines() {
        #expect(ApprovalToolPolicy.sessionAllowKey(toolName: "Bash", command: "ls") == "bash::ls")
        #expect(ApprovalToolPolicy.sessionAllowKey(toolName: "WebFetch", command: nil) == "webfetch")
        #expect(ApprovalToolPolicy.sessionAllowKey(toolName: "Edit", command: "") == "edit")
    }

    // MARK: - ApprovalSessionAllowList

    @Test("AllowList Allow-always sonrasi auto-allow doner")
    @MainActor
    func allowList_allowSession_autoAllow() {
        let list = ApprovalSessionAllowList()
        let key = ApprovalToolPolicy.sessionAllowKey(toolName: "Edit", command: nil)
        list.remember(key: key)

        let policy = list.policy(
            toolName: "Edit",
            command: nil,
            defaultPolicy: .prompt(risk: .high)
        )
        #expect(policy == .autoAllow)
    }

    @Test("AllowList ilgisiz tool default'u korur")
    @MainActor
    func allowList_unrelated_keepsDefault() {
        let list = ApprovalSessionAllowList()
        list.remember(key: ApprovalToolPolicy.sessionAllowKey(toolName: "Edit", command: nil))

        let policy = list.policy(
            toolName: "Bash",
            command: "rm -rf",
            defaultPolicy: .prompt(risk: .high)
        )
        #expect(policy == .prompt(risk: .high))
    }

    @Test("AllowList clear tum allow'lari siler")
    @MainActor
    func allowList_clear() {
        let list = ApprovalSessionAllowList()
        list.remember(key: "x")
        #expect(list.contains(key: "x") == true)
        list.clear()
        #expect(list.contains(key: "x") == false)
    }
}
