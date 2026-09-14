using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace LegalAssistant.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRiskSeverityAndColor : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "Severity",
                table: "RiskyClauses",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "SeverityColor",
                table: "RiskyClauses",
                type: "nvarchar(max)",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "Severity",
                table: "RiskyClauses");

            migrationBuilder.DropColumn(
                name: "SeverityColor",
                table: "RiskyClauses");
        }
    }
}
