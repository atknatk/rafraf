import Foundation
import Testing
@testable import RafRaf

/// NotificationMapper DTO <-> Domain donusum testleri.
@Suite("NotificationMapper Tests")
struct NotificationMapperTests {

    // MARK: - DeviceTokenRegisterResponseDTO -> DeviceTokenRegistration

    @Test("DeviceTokenRegisterResponseDTO domain modeline donmeli")
    func deviceTokenResponseToDomain() {
        let id = UUID()
        let date = Date()
        let dto = DeviceTokenRegisterResponseDTO(id: id, registeredAt: date)

        let domain = NotificationMapper.toDomain(dto)

        #expect(domain.id == id)
        #expect(domain.registeredAt == date)
    }

    // MARK: - NotificationSettingsDTO -> NotificationPreferences

    @Test("NotificationSettingsDTO domain modeline donmeli")
    func settingsToDomain() {
        let dto = NotificationSettingsDTO(
            taskCompleteEnabled: true,
            approvalNeededEnabled: false,
            errorEnabled: true,
            infoEnabled: false
        )

        let domain = NotificationMapper.toDomain(dto)

        #expect(domain.taskCompleteEnabled == true)
        #expect(domain.approvalNeededEnabled == false)
        #expect(domain.errorEnabled == true)
        #expect(domain.infoEnabled == false)
    }

    @Test("Tum degerler true olan DTO dogru donmeli")
    func settingsAllTrue() {
        let dto = NotificationSettingsDTO(
            taskCompleteEnabled: true,
            approvalNeededEnabled: true,
            errorEnabled: true,
            infoEnabled: true
        )

        let domain = NotificationMapper.toDomain(dto)

        #expect(domain.taskCompleteEnabled == true)
        #expect(domain.approvalNeededEnabled == true)
        #expect(domain.errorEnabled == true)
        #expect(domain.infoEnabled == true)
    }

    // MARK: - NotificationPreferencesUpdate -> NotificationSettingsUpdateDTO

    @Test("Kısmi guncelleme DTO'ya donmeli")
    func partialUpdateToDTO() {
        let update = NotificationPreferencesUpdate(
            taskCompleteEnabled: false,
            approvalNeededEnabled: nil,
            errorEnabled: nil,
            infoEnabled: nil
        )

        let dto = NotificationMapper.toDTO(update)

        #expect(dto.taskCompleteEnabled == false)
        #expect(dto.approvalNeededEnabled == nil)
        #expect(dto.errorEnabled == nil)
        #expect(dto.infoEnabled == nil)
    }

    @Test("Tum alanlar dolu guncelleme DTO'ya donmeli")
    func fullUpdateToDTO() {
        let update = NotificationPreferencesUpdate(
            taskCompleteEnabled: true,
            approvalNeededEnabled: false,
            errorEnabled: true,
            infoEnabled: false
        )

        let dto = NotificationMapper.toDTO(update)

        #expect(dto.taskCompleteEnabled == true)
        #expect(dto.approvalNeededEnabled == false)
        #expect(dto.errorEnabled == true)
        #expect(dto.infoEnabled == false)
    }
}
