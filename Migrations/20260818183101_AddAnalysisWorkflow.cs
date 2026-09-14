using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace LegalAssistant.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddAnalysisWorkflow : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "CompletedAt",
                table: "ContractAnalyses",
                type: "datetime2",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ErrorMessage",
                table: "ContractAnalyses",
                type: "nvarchar(2000)",
                maxLength: 2000,
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "StartedAt",
                table: "ContractAnalyses",
                type: "datetime2",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Status",
                table: "ContractAnalyses",
                type: "nvarchar(20)",
                maxLength: 20,
                nullable: false,
                defaultValue: "Pending");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "CompletedAt",
                table: "ContractAnalyses");

            migrationBuilder.DropColumn(
                name: "ErrorMessage",
                table: "ContractAnalyses");

            migrationBuilder.DropColumn(
                name: "StartedAt",
                table: "ContractAnalyses");

            migrationBuilder.DropColumn(
                name: "Status",
                table: "ContractAnalyses");
        }
    }
}
