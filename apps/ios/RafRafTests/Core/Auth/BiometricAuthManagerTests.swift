import Foundation
import Testing
@testable import RafRaf

/// BiometricAuthManager testleri.
@Suite("BiometricAuthManager Tests")
struct BiometricAuthManagerTests {

    @Test("availableBiometricType deger donmeli")
    func biometricTypeReturnsValue() {
        let manager = BiometricAuthManager()
        // Simulator'da genelde .none doner ama crash olmamali
        let biometricType = manager.availableBiometricType
        // BiometricType enum'undan bir deger donmeli
        #expect(biometricType == .none || biometricType == .faceID || biometricType == .touchID || biometricType == .opticID)
    }

    @Test("isBiometricAvailable tutarli olmali")
    func isBiometricAvailableConsistent() {
        let manager = BiometricAuthManager()
        let isAvailable = manager.isBiometricAvailable
        let biometricType = manager.availableBiometricType

        if biometricType == .none {
            #expect(isAvailable == false)
        } else {
            #expect(isAvailable == true)
        }
    }
}
