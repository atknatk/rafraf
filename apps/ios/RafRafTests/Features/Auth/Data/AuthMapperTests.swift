import Foundation
import Testing
@testable import RafRaf

/// AuthMapper testleri.
@Suite("AuthMapper Tests")
struct AuthMapperTests {

    @Test("toDomain DTO'yu dogru domain modeline donusturmeli")
    func toDomainMapsCorrectly() {
        let dto = TokenResponseDTO(
            accessToken: "access-123",
            refreshToken: "refresh-456",
            tokenType: "bearer",
            expiresIn: 900
        )

        let authToken = AuthMapper.toDomain(dto)

        #expect(authToken.accessToken == "access-123")
        #expect(authToken.refreshToken == "refresh-456")
        #expect(authToken.tokenType == "bearer")
        #expect(authToken.expiresIn == 900)
        #expect(authToken.expiresAt > Date())
    }

    @Test("toDomain expiresAt dogru hesaplanmali")
    func toDomainExpiresAtCalculation() {
        let dto = TokenResponseDTO(
            accessToken: "token",
            refreshToken: "refresh",
            tokenType: "bearer",
            expiresIn: 3600
        )

        let before = Date()
        let authToken = AuthMapper.toDomain(dto)
        let after = Date()

        let expectedMin = before.addingTimeInterval(3600)
        let expectedMax = after.addingTimeInterval(3600)

        #expect(authToken.expiresAt >= expectedMin)
        #expect(authToken.expiresAt <= expectedMax)
    }

    @Test("toDomain sifir expiresIn durumu")
    func toDomainZeroExpiresIn() {
        let dto = TokenResponseDTO(
            accessToken: "token",
            refreshToken: "refresh",
            tokenType: "bearer",
            expiresIn: 0
        )

        let authToken = AuthMapper.toDomain(dto)
        #expect(authToken.expiresIn == 0)
    }
}
