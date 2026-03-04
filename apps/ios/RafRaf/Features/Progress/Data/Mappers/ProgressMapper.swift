import Foundation

/// Progress DTO'larini domain modellere donusturur.
enum ProgressMapper {
    /// ProgressEventDTO'yu (basit veya zengin WS mesaji) ProgressState domain modeline donusturur.
    /// Zenginlestirilmis `stepsDetail` varsa detayli timeline, yoksa basit mapping kullanir.
    /// - Parameter dto: Backend'den gelen progress event DTO'su
    /// - Returns: Domain ProgressState modeli
    static func toDomain(from dto: ProgressEventDTO) -> ProgressState {
        // Zenginlestirilmis step bilgisi varsa onu kullan
        if let stepsDetail = dto.stepsDetail, !stepsDetail.isEmpty {
            let steps = stepsDetail.map { toDomain(from: $0) }
            let activeIndex = steps.firstIndex { $0.status == .active }
            let status: ProgressOverallStatus = dto.phase == "completed" ? .completed : .running

            return ProgressState(
                mode: .determinate,
                percentage: dto.percentage,
                taskDescription: dto.task,
                steps: steps,
                currentStepIndex: activeIndex,
                status: status
            )
        }

        // Basit fallback
        let mode: ProgressMode = dto.totalSteps > 0 ? .determinate : .indeterminate
        let steps = generateSteps(currentStep: dto.step, totalSteps: dto.totalSteps)
        let currentIndex = dto.step > 0 ? dto.step - 1 : nil
        let status: ProgressOverallStatus = dto.percentage >= 100 ? .completed : .running

        return ProgressState(
            mode: mode,
            percentage: dto.percentage,
            taskDescription: dto.task,
            steps: steps,
            currentStepIndex: currentIndex,
            status: status
        )
    }

    /// ProgressStateDTO'yu (detayli durum) ProgressState domain modeline donusturur.
    /// - Parameter dto: Backend'den gelen detayli progress state DTO'su
    /// - Returns: Domain ProgressState modeli
    static func toDomain(from dto: ProgressStateDTO) -> ProgressState {
        let mode = ProgressMode(rawValue: dto.mode ?? "indeterminate") ?? .indeterminate
        let status = ProgressOverallStatus(rawValue: dto.status ?? "running") ?? .running
        let steps = dto.steps?.map { stepDTO in
            toDomain(from: stepDTO)
        } ?? []

        return ProgressState(
            id: dto.id,
            mode: mode,
            percentage: dto.percentage,
            taskDescription: dto.taskDescription,
            steps: steps,
            currentStepIndex: dto.currentStepIndex,
            status: status
        )
    }

    /// ProgressStepDTO'yu ProgressStep domain modeline donusturur.
    /// - Parameter dto: Backend'den gelen step DTO'su
    /// - Returns: Domain ProgressStep modeli
    static func toDomain(from dto: ProgressStepDTO) -> ProgressStep {
        let type = ProgressStepType(rawValue: dto.stepType) ?? .thinking
        let status = ProgressStepStatus(rawValue: dto.status) ?? .pending

        // toolName varsa detay olarak ekle
        let detail: String?
        if let toolName = dto.toolName, let existingDetail = dto.detail {
            detail = "\(toolName): \(existingDetail)"
        } else if let toolName = dto.toolName {
            detail = toolName
        } else {
            detail = dto.detail
        }

        return ProgressStep(
            id: dto.id,
            type: type,
            label: dto.label,
            status: status,
            durationSeconds: dto.durationSeconds,
            detail: detail
        )
    }

    // MARK: - Private

    /// Basit step/totalSteps bilgisinden ProgressStep listesi olusturur.
    private static func generateSteps(currentStep: Int, totalSteps: Int) -> [ProgressStep] {
        guard totalSteps > 0 else { return [] }

        return (1...totalSteps).map { index in
            let status: ProgressStepStatus
            if index < currentStep {
                status = .completed
            } else if index == currentStep {
                status = .active
            } else {
                status = .pending
            }

            return ProgressStep(
                id: "step-\(index)",
                type: .thinking,
                label: String(localized: "progress.step.\(index)of\(totalSteps)"),
                status: status
            )
        }
    }
}
