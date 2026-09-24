using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace LegalAssistant.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddedP4 : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "AiRequestId",
                table: "ChatMessages",
                type: "nvarchar(100)",
                maxLength: 100,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "CitationsJson",
                table: "ChatMessages",
                type: "nvarchar(max)",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "InsufficientEvidence",
                table: "ChatMessages",
                type: "bit",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "ModelTag",
                table: "ChatMessages",
                type: "nvarchar(100)",
                maxLength: 100,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AiRequestId",
                table: "ChatMessages");

            migrationBuilder.DropColumn(
                name: "CitationsJson",
                table: "ChatMessages");

            migrationBuilder.DropColumn(
                name: "InsufficientEvidence",
                table: "ChatMessages");

            migrationBuilder.DropColumn(
                name: "ModelTag",
                table: "ChatMessages");
        }
    }
}
