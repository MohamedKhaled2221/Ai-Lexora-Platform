using FluentValidation;
using LegalAssistant.Api.Documents;

namespace LegalAssistant.Api.Validators;

public class UpdateDocumentRequestValidator : AbstractValidator<UpdateDocumentRequest>
{
    public UpdateDocumentRequestValidator()
    {
        RuleFor(x => x).Must(x => x.FileName is not null || x.Type is not null)
            .WithMessage("File name or document type is required.");
        When(x => x.FileName is not null, () => RuleFor(x => x.FileName!).NotEmpty().MaximumLength(260));
        When(x => x.Type is not null, () => RuleFor(x => x.Type!).NotEmpty().MaximumLength(50));
    }
}

public class CompleteAnalysisRequestValidator : AbstractValidator<CompleteAnalysisRequest>
{
    public CompleteAnalysisRequestValidator()
    {
        RuleFor(x => x.RiskScore).InclusiveBetween(0, 100);
        RuleFor(x => x.Summary).NotEmpty().MaximumLength(2000);
        RuleForEach(x => x.RiskyClauses).SetValidator(new CreateRiskyClauseRequestValidator()).When(x => x.RiskyClauses is not null);
    }
}

public class CreateRiskyClauseRequestValidator : AbstractValidator<CreateRiskyClauseRequest>
{
    public CreateRiskyClauseRequestValidator()
    {
        RuleFor(x => x.ClauseText).NotEmpty().MaximumLength(2000);
        RuleFor(x => x.RiskType).NotEmpty().MaximumLength(50);
        RuleFor(x => x.Explanation).NotEmpty().MaximumLength(1000);
    }
}

public class FailAnalysisRequestValidator : AbstractValidator<FailAnalysisRequest>
{
    public FailAnalysisRequestValidator() => RuleFor(x => x.ErrorMessage).NotEmpty().MaximumLength(2000);
}
