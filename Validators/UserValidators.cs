using FluentValidation;
using LegalAssistant.Api.Data;
using LegalAssistant.Api.Users;

namespace LegalAssistant.Api.Validators;

public class UpdateProfileRequestValidator : AbstractValidator<UpdateProfileRequest>
{
    public UpdateProfileRequestValidator() => RuleFor(x => x.FullName).NotEmpty().MaximumLength(150);
}

public class ChangePasswordRequestValidator : AbstractValidator<ChangePasswordRequest>
{
    public ChangePasswordRequestValidator()
    {
        RuleFor(x => x.CurrentPassword).NotEmpty();
        RuleFor(x => x.NewPassword).NotEmpty().MinimumLength(8).MaximumLength(100)
            .NotEqual(x => x.CurrentPassword).WithMessage("New password must be different from the current password.");
    }
}

public class UpdateUserRoleRequestValidator : AbstractValidator<UpdateUserRoleRequest>
{
    public UpdateUserRoleRequestValidator() => RuleFor(x => x.Role).Must(role => role is AppRoles.Admin or AppRoles.Lawyer)
        .WithMessage("Role must be Admin or Lawyer.");
}
