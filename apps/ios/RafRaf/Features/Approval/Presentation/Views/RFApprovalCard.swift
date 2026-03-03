import SwiftUI

/// Interaktif onay karti.
/// Kullanici onayi gerektiren islemler icin countdown timer ve secenek butonlari iceren kart.
/// Spring animasyonlu gosterim/kapanma destegi.
struct RFApprovalCard: View {
    @State private var viewModel: ApprovalCardViewModel

    init(viewModel: ApprovalCardViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        if let question = viewModel.question, viewModel.isVisible {
            RFCard(padding: RFSpacing.md, cornerRadius: 16) {
                VStack(alignment: .leading, spacing: RFSpacing.sm) {
                    headerView(question: question)
                    questionTextView(question: question)

                    if let context = question.context {
                        contextView(context: context)
                    }

                    optionButtonsView(question: question)

                    if viewModel.isDecided {
                        decidedView
                    }

                    if let errorMessage = viewModel.errorMessage {
                        errorView(message: errorMessage)
                    }
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .strokeBorder(
                        viewModel.isDangerousCategory
                            ? RFColors.error.opacity(0.5)
                            : RFColors.fallbackPrimary.opacity(0.3),
                        lineWidth: 1.5
                    )
            )
            .transition(.asymmetric(
                insertion: .scale(scale: 0.9).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
            .animation(.spring(response: 0.4, dampingFraction: 0.8), value: viewModel.isVisible)
            .animation(.spring(response: 0.3, dampingFraction: 0.9), value: viewModel.isDecided)
            .accessibilityElement(children: .contain)
            .accessibilityLabel(
                String(localized: "approval.card.accessibilityLabel")
            )
        }
    }

    // MARK: - Header

    private func headerView(question: ApprovalQuestion) -> some View {
        HStack {
            categoryBadge(category: question.category)
            Spacer()
            if !viewModel.isDecided {
                RFCountdownTimer(
                    remainingSeconds: viewModel.remainingSeconds,
                    progress: viewModel.progressFraction,
                    isDangerous: viewModel.isDangerousCategory
                )
            }
        }
    }

    private func categoryBadge(category: ApprovalCategory) -> some View {
        RFText(
            categoryLabel(for: category),
            style: .captionBold,
            color: viewModel.isDangerousCategory ? RFColors.error : RFColors.fallbackPrimary
        )
        .padding(.horizontal, RFSpacing.xs)
        .padding(.vertical, RFSpacing.xxs)
        .background(
            (viewModel.isDangerousCategory ? RFColors.error : RFColors.fallbackPrimary)
                .opacity(0.1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Question

    private func questionTextView(question: ApprovalQuestion) -> some View {
        RFText(question.question, style: .bodyBold)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func contextView(context: String) -> some View {
        RFText(context, style: .caption)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Options

    private func optionButtonsView(question: ApprovalQuestion) -> some View {
        VStack(spacing: RFSpacing.xs) {
            ForEach(question.options) { option in
                RFApprovalOptionButton(
                    option: option,
                    isDisabled: viewModel.isDecided || viewModel.isSubmitting,
                    isLoading: viewModel.isSubmitting && !viewModel.isDecided
                ) {
                    let decision: ApprovalDecision = option.id == "approve"
                        ? .approved
                        : .rejected
                    Task {
                        await viewModel.submitDecision(
                            optionId: option.id,
                            decision: decision
                        )
                    }
                }
            }
        }
    }

    // MARK: - Decided

    private var decidedView: some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(RFColors.success)
            RFText(
                String(localized: "approval.decided"),
                style: .caption,
                color: RFColors.success
            )
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, RFSpacing.xxs)
        .onAppear {
            // Karar sonrasi karti 2 saniye sonra kapat
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                viewModel.dismiss()
            }
        }
    }

    // MARK: - Error

    private func errorView(message: String) -> some View {
        HStack(spacing: RFSpacing.xs) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(RFColors.error)
            RFText(message, style: .caption, color: RFColors.error)
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - Helpers

    private func categoryLabel(for category: ApprovalCategory) -> String {
        switch category {
        case .deploy:
            return String(localized: "approval.category.deploy")
        case .destructive:
            return String(localized: "approval.category.destructive")
        case .infrastructure:
            return String(localized: "approval.category.infrastructure")
        case .writeRemote:
            return String(localized: "approval.category.writeRemote")
        }
    }
}

#Preview("Standard Approval") {
    let viewModel = ApprovalCardViewModel(
        submitDecisionUseCase: SubmitApprovalDecisionUseCase(
            repository: PreviewApprovalRepository()
        )
    )

    VStack {
        RFApprovalCard(viewModel: viewModel)
    }
    .padding()
    .task {
        await MainActor.run {
            viewModel.showQuestion(
                ApprovalQuestion(
                    id: UUID().uuidString,
                    question: "Docker container'i production ortamina deploy etmek istiyor musunuz?",
                    context: "Image: rafraf-backend:v1.2.0 -> EKS production cluster",
                    options: [
                        ApprovalOption(id: "approve", label: "Onayla", style: .primary),
                        ApprovalOption(id: "reject", label: "Reddet", style: .danger)
                    ],
                    timeoutSeconds: 30,
                    category: .deploy,
                    receivedAt: Date()
                )
            )
        }
    }
}

#Preview("Multi-Choice") {
    let viewModel = ApprovalCardViewModel(
        submitDecisionUseCase: SubmitApprovalDecisionUseCase(
            repository: PreviewApprovalRepository()
        )
    )

    VStack {
        RFApprovalCard(viewModel: viewModel)
    }
    .padding()
    .task {
        await MainActor.run {
            viewModel.showQuestion(
                ApprovalQuestion(
                    id: UUID().uuidString,
                    question: "Veritabani migration'i calistirmak istiyor musunuz?",
                    context: "Migration: 003_add_approval_requests_table.sql",
                    options: [
                        ApprovalOption(id: "approve", label: "Onayla", style: .primary),
                        ApprovalOption(id: "detail", label: "Detay Gor", style: .secondary),
                        ApprovalOption(id: "reject", label: "Reddet", style: .danger)
                    ],
                    timeoutSeconds: 60,
                    category: .infrastructure,
                    receivedAt: Date()
                )
            )
        }
    }
}

#Preview("Destructive Category") {
    let viewModel = ApprovalCardViewModel(
        submitDecisionUseCase: SubmitApprovalDecisionUseCase(
            repository: PreviewApprovalRepository()
        )
    )

    VStack {
        RFApprovalCard(viewModel: viewModel)
    }
    .padding()
    .task {
        await MainActor.run {
            viewModel.showQuestion(
                ApprovalQuestion(
                    id: UUID().uuidString,
                    question: "Tum gecici dosyalari silmek istiyor musunuz?",
                    context: nil,
                    options: [
                        ApprovalOption(id: "approve", label: "Sil", style: .danger),
                        ApprovalOption(id: "reject", label: "Iptal", style: .secondary)
                    ],
                    timeoutSeconds: 15,
                    category: .destructive,
                    receivedAt: Date()
                )
            )
        }
    }
}

/// Preview icin mock repository.
private final class PreviewApprovalRepository: ApprovalRepositoryProtocol, @unchecked Sendable {
    func submitDecision(
        approvalId: String,
        decision: ApprovalDecision,
        note: String?
    ) async throws {
        // Simulate network delay
        try? await Task.sleep(for: .milliseconds(500))
    }
}
