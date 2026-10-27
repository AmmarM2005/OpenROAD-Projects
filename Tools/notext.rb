# notext.rb : hide text objects (net/pin/instance labels) so the layout is readable; View > Show Text brings them back
begin
  RBA::Application.instance.main_window.set_config("text-visible", "false")
rescue => e
  puts "notext.rb: #{e}"
end
