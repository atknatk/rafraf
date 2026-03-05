import SwiftUI

/// Proje olusturma ve duzenleme formu ekrani.
/// `viewModel.isEditMode` degerine gore baslik degisir.
struct ProjectFormView: View {
    @State private var viewModel: ProjectFormViewModel
    @Environment(\.dismiss) private var dismiss

    init(viewModel: ProjectFormViewModel) {
        self._viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: RFSpacing.md) {
                    nameField
                    descriptionField
                    repositoryURLField
                    localPathField
                    techStackField
                    saveButton
                }
                .padding(.horizontal, RFSpacing.md)
                .padding(.vertical, RFSpacing.sm)
            }
            .background(RFColors.fallbackBackground)
            .navigationTitle(
                viewModel.isEditMode
                    ? String(localized: "project.form.title.edit")
                    : String(localized: "project.form.title.create")
            )
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    RFButton(
                        String(localized: "project.action.cancel"),
                        style: .ghost,
                        size: .small
                    ) {
                        dismiss()
                    }
                }
            }
            .onChange(of: viewModel.didSave) { _, saved in
                if saved { dismiss() }
            }
            .overlay {
                if let errorMessage = viewModel.errorMessage {
                    errorBanner(message: errorMessage)
                }
            }
        }
    }

    // MARK: - Fields

    private var nameField: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            fieldLabel(
                String(localized: "project.form.field.name"),
                required: true
            )
            RFTextField(
                String(localized: "project.form.placeholder.name"),
                text: $viewModel.name,
                errorMessage: viewModel.name.isEmpty && viewModel.errorMessage != nil
                    ? String(localized: "project.form.error.nameRequired")
                    : nil,
                leadingIcon: "folder"
            )
        }
    }

    private var descriptionField: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            fieldLabel(String(localized: "project.form.field.description"))
            RFTextField(
                String(localized: "project.form.placeholder.description"),
                text: $viewModel.description,
                mode: .multiline,
                leadingIcon: "text.alignleft"
            )
        }
    }

    private var repositoryURLField: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            fieldLabel(String(localized: "project.form.field.repositoryURL"))
            RFTextField(
                String(localized: "project.form.placeholder.repositoryURL"),
                text: $viewModel.repositoryURL,
                leadingIcon: "link"
            )
        }
    }

    private var localPathField: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            fieldLabel(String(localized: "project.form.field.localPath"))
            RFTextField(
                String(localized: "project.form.placeholder.localPath"),
                text: $viewModel.localPath,
                leadingIcon: "folder.badge.gearshape"
            )
        }
    }

    private var techStackField: some View {
        VStack(alignment: .leading, spacing: RFSpacing.xxs) {
            fieldLabel(String(localized: "project.form.field.techStack"))
            RFTextField(
                String(localized: "project.form.placeholder.techStack"),
                text: $viewModel.techStackInput,
                leadingIcon: "cpu"
            )
            RFText(
                String(localized: "project.form.hint.techStack"),
                style: .caption,
                color: RFColors.fallbackTextTertiary
            )
            .padding(.horizontal, RFSpacing.xxs)
        }
    }

    private var saveButton: some View {
        RFButton(
            viewModel.isEditMode
                ? String(localized: "project.form.button.save")
                : String(localized: "project.form.button.create"),
            style: .primary,
            isLoading: viewModel.isLoading,
            isDisabled: !viewModel.nameIsValid
        ) {
            Task { await viewModel.save() }
        }
        .padding(.top, RFSpacing.sm)
    }

    // MARK: - Helpers

    private func fieldLabel(_ title: String, required: Bool = false) -> some View {
        HStack(spacing: RFSpacing.xxs) {
            RFText(title, style: .captionBold)
            if required {
                RFText("*", style: .captionBold, color: RFColors.error)
            }
        }
        .padding(.horizontal, RFSpacing.xxs)
    }

    private func errorBanner(message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(RFColors.error)
                RFText(message, style: .body, color: .white)
                    .lineLimit(2)
                Spacer()
                RFButton(
                    String(localized: "project.error.dismiss"),
                    style: .ghost,
                    size: .small
                ) {
                    viewModel.dismissError()
                }
            }
            .padding(RFSpacing.sm)
            .background(RFColors.error.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: RFCornerRadius.medium))
            .padding(.horizontal, RFSpacing.md)
            .padding(.top, RFSpacing.xs)

            Spacer()
        }
    }
}

#Preview("Create") {
    ProjectFormView(
        viewModel: ProjectFormViewModel(
            repository: PreviewProjectRepository(),
            projectId: nil
        )
    )
}

#Preview("Edit") {
    ProjectFormView(
        viewModel: ProjectFormViewModel(
            repository: PreviewProjectRepository(),
            projectId: "preview-id",
            existingProject: Project(
                id: "preview-id",
                name: "RafRaf",
                description: "AI-driven proje yonetim sistemi",
                status: .active,
                repositoryURL: "https://github.com/atknatk/rafraf",
                localPath: "/Users/dev/rafraf",
                techStack: ["Swift", "Python", "FastAPI"]
            )
        )
    )
}
