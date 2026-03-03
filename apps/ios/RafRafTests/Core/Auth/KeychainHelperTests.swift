import Foundation
import Testing
@testable import RafRaf

/// KeychainHelper testleri.
@Suite("KeychainHelper Tests")
struct KeychainHelperTests {
    private let keychain = KeychainHelper(service: "com.rafraf.test")

    @Test("String kaydetme ve okuma basarili olmali")
    func saveAndReadString() throws {
        let key = "test-key-\(UUID().uuidString)"
        let value = "test-value-123"

        try keychain.saveString(value, for: key)
        let readValue = keychain.readString(for: key)

        #expect(readValue == value)

        // Temizlik
        try keychain.delete(for: key)
    }

    @Test("Data kaydetme ve okuma basarili olmali")
    func saveAndReadData() throws {
        let key = "test-data-\(UUID().uuidString)"
        let data = "test-data".data(using: .utf8)!

        try keychain.save(data, for: key)
        let readData = keychain.read(for: key)

        #expect(readData == data)

        // Temizlik
        try keychain.delete(for: key)
    }

    @Test("Olmayan anahtar icin nil donmeli")
    func readNonExistentKey() {
        let result = keychain.readString(for: "non-existent-key-\(UUID().uuidString)")
        #expect(result == nil)
    }

    @Test("Silme basarili olmali")
    func deleteKey() throws {
        let key = "test-delete-\(UUID().uuidString)"
        try keychain.saveString("value", for: key)

        try keychain.delete(for: key)

        let result = keychain.readString(for: key)
        #expect(result == nil)
    }

    @Test("Ayni anahtara tekrar yazma guncelleme yapmali")
    func overwriteKey() throws {
        let key = "test-overwrite-\(UUID().uuidString)"

        try keychain.saveString("value1", for: key)
        try keychain.saveString("value2", for: key)

        let result = keychain.readString(for: key)
        #expect(result == "value2")

        // Temizlik
        try keychain.delete(for: key)
    }

    @Test("Toplu silme basarili olmali")
    func deleteAll() throws {
        let testKeychain = KeychainHelper(service: "com.rafraf.test.deleteall.\(UUID().uuidString)")
        try testKeychain.saveString("val1", for: "key1")
        try testKeychain.saveString("val2", for: "key2")

        try testKeychain.deleteAll()

        #expect(testKeychain.readString(for: "key1") == nil)
        #expect(testKeychain.readString(for: "key2") == nil)
    }

    @Test("Olmayan anahtari silmek hata vermemeli")
    func deleteNonExistent() throws {
        try keychain.delete(for: "non-existent-\(UUID().uuidString)")
        // Hata atilmamali
    }
}
