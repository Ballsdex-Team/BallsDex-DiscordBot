# credit me somewhere
# I kinda redid this
# /gu bhinjidk if it works  
ball_id="Specific ball ID to drop (leave empty for random)",
channel="Channel to drop the ball in (defaults to current channel)"
async def drop(
    self,
    interaction: discord.Interaction,
    ball_id: int = None,
    channel: discord.TextChannel = None
) -> None:
    """
    Manually spawn a ball in the specified channel.
    
    This command requires the "Manage Server" permission.
    """
    await interaction.response.defer(ephemeral=True)
    
    # Use current channel if none specified
    target_channel = channel or interaction.channel
    
    # Check if channel is valid for drops
    if not target_channel.permissions_for(interaction.guild.me).send_messages:
        return await interaction.followup.send(
            f"I don't have permission to send messages in {target_channel.mention}.",
            ephemeral=True
        )
    
    guild_config = await GuildConfig.get_or_none(guild_id=interaction.guild.id)
    if not guild_config or not guild_config.enabled:
        return await interaction.followup.send(
            "Balls spawning is not enabled on this server. Please use `/config` to enable it first.",
            ephemeral=True
        )
    
    # If ball_id provided, get that specific ball
    if ball_id:
        ball = await Ball.get_or_none(pk=ball_id)
        if not ball:
            return await interaction.followup.send(
                f"Ball with ID {ball_id} does not exist.", 
                ephemeral=True
            )
    # Otherwise select a random ball
    else:
        balls = await Ball.all()
        if not balls:
            return await interaction.followup.send(
                "There are no balls in the database.", 
                ephemeral=True
            )
        ball = random.choice(balls)
    
    self.bot.logger.info(
        f"Manual drop triggered by {interaction.user} (ID: {interaction.user.id}) "
        f"in guild {interaction.guild} (ID: {interaction.guild.id}), "
        f"channel: {target_channel} (ID: {target_channel.id}), "
        f"ball: {ball.country} (ID: {ball.pk})"
    )
    
    await interaction.followup.send(
        f"Spawning {format_emoji(ball.emoji)} {ball.country} ball in {target_channel.mention}!",
        ephemeral=True
    )
    
    # Use the drop manager to handle the spawning process
    await self.drop_manager.spawn_ball(target_channel, ball)
